"""Durable contract workflow: specialist agents propose, users decide, code renders."""

import asyncio
import uuid
from hashlib import sha256

from app.agents.coverage_recovery import review_coverage
from app.agents.coverage_repair import repair_coverage
from app.agents.field_coordinator import FieldCoordinationResult, FieldCoordinator
from app.agents.negotiation_coordinator import NegotiationCoordinator
from app.agents.team import create_agent_team
from app.config import Settings
from app.documents.slot_constraints import validate_slot_values
from app.domain.contract_workflow import AgentEvent, ContractWorkspace, FieldStatus, ReviewedField
from app.domain.errors import InvalidContractInput, WorkspaceConflict
from app.model_client import ModelUnavailable
from app.observability import finish_run, observed, operations
from app.repositories.contract_workspaces import ContractWorkspaceRepository, utc_timestamp
from app.services.contract_templates import ContractTemplateCatalog
from app.services.source_records import number_source_lines, validate_source_text


class ContractWorkflowService:
    """协调任务状态、人机审批和生成文件归属的领域服务。"""

    def __init__(
        self, repository: ContractWorkspaceRepository, catalog: ContractTemplateCatalog, settings: Settings
    ):
        """注入依赖并初始化本实例的状态，保持资源所有权与其他请求隔离。

        Args:
            repository: 负责用户隔离与修订控制的仓储。
            catalog: 受控的原始模板目录及检索/写入服务。
            settings: 已解析的运行配置，包含路径、模型及预算；不得公开密钥。
        """
        self.repository = repository
        self.catalog = catalog
        self.settings = settings

    def create(self, user_id: int, title: str, source_name: str, source_text: str) -> ContractWorkspace:
        """校验纪要后创建用户归属任务，并记录导入事件。

        Args:
            user_id: 当前访问资源的账户标识。
            title: 用户指定的任务或模板名称。
            source_name: 纪要来源的展示名称。
            source_text: 尚未被模型改写的原始协商记录。
        """
        source_text = validate_source_text(source_text, self.settings)
        now = utc_timestamp()
        workspace = ContractWorkspace(
            id=uuid.uuid4().hex,
            title=title.strip() or "新的合同任务",
            source_name=source_name,
            source_text=source_text,
            created_at=now,
            updated_at=now,
        )
        self._event(workspace, "user", "import_source", f"导入 {len(source_text)} 字符的协商记录")
        return self.repository.create(workspace, user_id)

    def _load(self, workspace_id: str, user_id: int, revision: int) -> ContractWorkspace:
        """同时验证任务归属及预期修订号，防止旧页面覆盖状态。

        Args:
            workspace_id: 需要校验归属的合同任务标识。
            user_id: 当前访问资源的账户标识。
            revision: 调用方持有的任务修订号。
        """
        workspace = self.repository.get(workspace_id, user_id)
        if workspace.revision != revision:
            raise WorkspaceConflict("页面已过期，请重新打开任务后再操作")
        return workspace

    def rename(self, workspace_id: str, user_id: int, revision: int, title: str) -> ContractWorkspace:
        """仅修改任务名称，并以比较交换方式保存新修订。

        Args:
            workspace_id: 需要校验归属的合同任务标识。
            user_id: 当前访问资源的账户标识。
            revision: 调用方持有的任务修订号。
            title: 用户指定的任务或模板名称。
        """
        workspace = self._load(workspace_id, user_id, revision)
        if not title.strip():
            raise InvalidContractInput("任务名称不能为空")
        workspace.title = title.strip()
        return self.repository.save(workspace, user_id, revision)

    def delete(self, workspace_id: str, user_id: int) -> None:
        """删除归属已核验的任务与生成文件，不对目录执行递归删除。

        Args:
            workspace_id: 需要校验归属的合同任务标识。
            user_id: 当前访问资源的账户标识。
        """
        filenames = self.repository.delete(workspace_id, user_id)
        root = self.settings.generated_dir.resolve()
        for filename in filenames:
            path = (root / filename).resolve()
            if path.is_relative_to(root):
                path.unlink(missing_ok=True)

    @staticmethod
    def _event(workspace: ContractWorkspace, role: str, action: str, detail: str) -> None:
        """在任务内追加带角色、动作和统一时间戳的执行事件。

        Args:
            workspace: 当前合同任务领域快照。
            role: 本次事件所属的用户、模型角色或代码工具。
            action: 当前业务阶段或主控选择的受限动作。
            detail: 向用户展示的简短事件说明。
        """
        workspace.events.append(
            AgentEvent(role=role, action=action, detail=detail, created_at=utc_timestamp())
        )

    def _template_details(self, workspace: ContractWorkspace) -> dict:
        """校验原件及引擎指纹，拒绝用过期位置映射写入新版模板。

        Args:
            workspace: 当前合同任务领域快照。
        """
        if workspace.selected_template is None:
            raise InvalidContractInput("请先选择合同模板")
        template = self.catalog.get_template(workspace.selected_template["id"])
        fingerprint = sha256(template.path.read_bytes()).hexdigest()
        if workspace.selected_template.get("fingerprint") != fingerprint:
            raise WorkspaceConflict("模板文件已更新，请重新选择模板并审查字段")
        details = self.catalog.describe_template(template.id)
        if workspace.selected_template.get("schema_fingerprint") != details["schema_fingerprint"]:
            raise WorkspaceConflict("模板填写规则已更新，请重新选择模板并审查全部字段")
        if not details["fillable"]:
            raise InvalidContractInput("模板包含不支持的文档结构，请维护模板后使用")
        return details

    @observed("analyze")
    async def analyze(self, workspace_id: str, user_id: int, revision: int) -> ContractWorkspace:
        """提取交易类型、最终共识和检索意图；不选择模板或生成合同。

        Args:
            workspace_id: 需要校验归属的合同任务标识。
            user_id: 当前访问资源的账户标识。
            revision: 调用方持有的任务修订号。
        """
        workspace = self._load(workspace_id, user_id, revision)
        if workspace.selected_template is not None:
            raise InvalidContractInput("任务已选择模板；如需重新分析记录，请创建新的合同任务")
        async with create_agent_team(self.settings) as team:
            operations.update(message="主控 Agent 正在规划分析与模板检索")
            analysis, recommendations, questions, searches, warnings = await NegotiationCoordinator(
                team, self.catalog, self.settings
            ).run(number_source_lines(workspace.source_text), workspace.source_text)
        workspace.analysis = analysis
        workspace.recommendations = recommendations
        workspace.agent_questions = questions
        workspace.coordination_warnings = warnings
        workspace.stage = "template_selection"
        self._event(workspace, "analysis_agent", "analyze_record", analysis.summary[:500])
        self._event(
            workspace,
            "supervisor_agent",
            "coordinate_retrieval",
            f"主控根据观察执行了 {searches} 轮检索，并交由用户选择模板；提出 {len(questions)} 个补充问题",
        )
        self._event(
            workspace,
            "retrieval",
            "recommend_templates",
            f"检索到 {len(workspace.recommendations)} 个候选；用户可自行选择模板库中的其他模板",
        )
        finish_run(workspace)
        return self.repository.save(workspace, user_id, revision)

    def present_workspace(self, workspace):
        """为当前映射补充可读标签；指纹过期时仅提示重选，不错误重标旧字段。

        Args:
            workspace: 当前合同任务领域快照。
        """
        if workspace.selected_template:
            details = self.catalog.describe_template(workspace.selected_template["id"])
            if workspace.selected_template.get("schema_fingerprint") != details["schema_fingerprint"]:
                # Never relabel old locators with the meanings of a newer engine.
                workspace.selected_template["requires_reselection"] = True
                return workspace
            metadata = {field["name"]: field for field in details["fields"]}
            for field in workspace.fields:
                for key in (
                    "display_name",
                    "section",
                    "kind",
                    "value_type",
                    "component",
                    "date_group",
                    "choices",
                    "fixed_unit",
                ):
                    setattr(field, key, metadata.get(field.name, {}).get(key, getattr(field, key)))
        if workspace.stage == "field_review" and workspace.fields and all(
            field.status in (FieldStatus.CONFIRMED, FieldStatus.OMITTED) for field in workspace.fields
        ):
            workspace.stage = "ready_to_generate"
        return workspace

    def select_template(
        self, workspace_id: str, user_id: int, revision: int, template_id: str
    ) -> ContractWorkspace:
        """由用户明确选定原件，并重新建立字段映射与人工审核起点。

        Args:
            workspace_id: 需要校验归属的合同任务标识。
            user_id: 当前访问资源的账户标识。
            revision: 调用方持有的任务修订号。
            template_id: 模板目录中的受控标识。
        """
        workspace = self._load(workspace_id, user_id, revision)
        template = self.catalog.get_template(template_id)
        details = self.catalog.describe_template(template_id)
        if not details["fillable"]:
            raise InvalidContractInput(
                "此模板没有可安全填写的位置或含有不支持的结构，请查看模板详情并选择其他模板"
            )
        workspace.selected_template = {
            **template.public(),
            "fingerprint": sha256(template.path.read_bytes()).hexdigest(),
            "field_count": len(details["fields"]),
            "warnings": details["warnings"],
            "requires_visual_review": details["requires_visual_review"],
            "schema_fingerprint": details["schema_fingerprint"],
        }
        workspace.fields = [ReviewedField(**field) for field in details["fields"]]
        workspace.extraction_failures = []
        workspace.coverage_gaps = []
        workspace.coverage_status = "not_run"
        workspace.coverage_error = {}
        workspace.agent_questions = []
        workspace.coordination_warnings = []
        workspace.stage = "template_selected"
        self._event(workspace, "user", "select_template", f"用户选择：{template.name}；字段审核重新开始")
        return self.repository.save(workspace, user_id, revision)

    @observed("extract")
    async def extract_fields(
        self,
        workspace_id: str,
        user_id: int,
        revision: int,
        replace_reviewed: bool = False,
        retry_failed: bool = False,
    ) -> ContractWorkspace:
        """分批提取、复核并按需定向修正；失败批次和已有人工审核有独立保护。

        Args:
            workspace_id: 需要校验归属的合同任务标识。
            user_id: 当前访问资源的账户标识。
            revision: 调用方持有的任务修订号。
            replace_reviewed: 用户是否明确允许重新提取覆盖既有人工审核。
            retry_failed: 是否只重试未被人工审核的失败字段。
        """
        workspace = self._load(workspace_id, user_id, revision)
        if (
            not retry_failed
            and not replace_reviewed
            and any(
                field.status in (FieldStatus.CONFIRMED, FieldStatus.OMITTED) for field in workspace.fields
            )
        ):
            raise WorkspaceConflict("已有人工审核结果；重新提取需要明确选择覆盖人工审核")
        details = self._template_details(workspace)
        source_lines = number_source_lines(workspace.source_text)
        source_by_line = {line["line_number"]: line["text"] for line in source_lines}
        target_fields = details["fields"]
        review_only_names = set()
        if retry_failed:
            review_only_names = {name for failure in workspace.extraction_failures
                                 if failure.get("phase") == "review" for name in failure["field_names"]}
            failed_names = {
                name for failure in workspace.extraction_failures for name in failure["field_names"]
            }
            reviewed_names = {
                field.name
                for field in workspace.fields
                if field.status in (FieldStatus.CONFIRMED, FieldStatus.OMITTED)
            }
            target_fields = [
                field for field in target_fields if field["name"] in failed_names - reviewed_names
            ]
            if not target_fields and workspace.coverage_status not in ("failed", "unverified", "skipped"):
                raise InvalidContractInput("没有待重试的失败字段，或这些字段已被人工审核")
        batches = [
            target_fields[start : start + self.settings.fields_per_batch]
            for start in range(0, len(target_fields), self.settings.fields_per_batch)
        ]
        semaphore = asyncio.Semaphore(self.settings.agent_parallelism)
        operations.update(
            message="按模板分批提取与独立复核",
            batches=[
                {"index": index + 1, "status": "queued", "message": "等待处理"}
                for index in range(len(batches))
            ],
        )

        async with create_agent_team(self.settings) as team:

            async def extract_batch(index, template_fields: list[dict]) -> FieldCoordinationResult:
                """在并发额度内运行本批提取、复核和受限主控修正。

                Args:
                    index: 当前集合的内部索引。
                    template_fields: 当前批次可填写位置及附近文字、类型约束。
                """
                async with semaphore:
                    return await FieldCoordinator(team, self.settings).run(
                        source_lines, template_fields, index,
                        previous_fields=[item for item in workspace.fields
                                         if item.name in review_only_names and
                                         any(spec["name"] == item.name for spec in template_fields)],
                    )

            async def monitored_batch(index, batch):
                """为批次异常发布可观测状态，再交由汇总逻辑保留部分成功。

                Args:
                    index: 当前集合的内部索引。
                    batch: 当前批次的模板字段集合。
                """
                try:
                    return await extract_batch(index, batch)
                except Exception as error:
                    operations.batch(index, "failed", str(error)[:300])
                    raise

            extracted_batches = await asyncio.gather(
                *(monitored_batch(index, batch) for index, batch in enumerate(batches)),
                return_exceptions=True,
            )
        self._template_details(workspace)
        by_name = (
            {field.name: field for field in workspace.fields}
            if retry_failed
            else {field["name"]: ReviewedField(**field) for field in details["fields"]}
        )
        workspace.extraction_failures = []
        workspace.agent_questions = []
        workspace.coordination_warnings = []
        repair_count = 0
        failed_batch_count = 0
        reviewed_this_run = set()
        for index, (batch, result) in enumerate(zip(batches, extracted_batches)):
            if isinstance(result, Exception):
                failed_batch_count += 1
                operations.batch(index, "failed", str(result)[:300])
                if not isinstance(result, (ModelUnavailable, ValueError)):
                    raise result
                workspace.extraction_failures.append(
                    {
                        "field_names": [field["name"] for field in batch],
                        "message": str(result),
                        "error": result.public_error() if isinstance(result, ModelUnavailable) else {},
                    }
                )
            else:
                workspace.extraction_failures.extend(result.failures)
                failed_batch_count += bool(result.failures)
                failed_extract_names = {name for failure in result.failures if failure["phase"] == "extract"
                                        for name in failure["field_names"]}
                failed_names = {name for failure in result.failures for name in failure["field_names"]}
                by_name.update({field.name: field for field in result.fields if field.name not in failed_extract_names})
                reviewed_this_run.update(field.name for field in result.fields if field.name not in failed_names)
                workspace.agent_questions.extend(result.questions)
                workspace.coordination_warnings.extend(result.warnings)
                repair_count += result.repairs
        workspace.agent_questions = list(dict.fromkeys(workspace.agent_questions))[:20]
        workspace.coordination_warnings = list(dict.fromkeys(workspace.coordination_warnings))[:20]
        self._event(
            workspace,
            "supervisor_agent",
            "coordinate_fields",
            f"主控完成 {repair_count} 轮定向修正并再次复核；{len(workspace.agent_questions)} 个补充问题，所有候选仍待人工确认",
        )
        workspace.fields = [by_name[field["name"]] for field in details["fields"]]
        operations.update(message="正在对照完整纪要检查跨字段遗漏与模板文义")
        workspace.coverage_gaps = []
        workspace.coverage_error = {}
        try:
            if not reviewed_this_run and not (retry_failed and not target_fields):
                raise ModelUnavailable(
                    "本次所有字段批次均未完成，已跳过全合同覆盖检查",
                    code="coverage_skipped",
                    hint="请先重试失败批次，或手动补充字段并对照完整纪要核查。",
                    retryable=False,
                )
            async with create_agent_team(self.settings) as team:
                coverage = await review_coverage(team.coverage, source_lines, details["fields"], workspace.fields)
                workspace.coverage_gaps = [gap for gap in coverage.gaps
                    if gap.evidence.quote in source_by_line.get(gap.evidence.line_number, "")]
                repaired, warnings = await repair_coverage(
                    team, source_lines, details["fields"], workspace.fields, coverage.gaps,
                    limit=min(5, self.settings.fields_per_batch))
                workspace.coordination_warnings.extend(warnings)
                if repaired:
                    # One repair round only; a fresh full comparison checks for regressions.
                    workspace.coverage_gaps = [gap for gap in coverage.gaps
                        if gap.evidence.quote in source_by_line.get(gap.evidence.line_number, "")]
                    coverage = await review_coverage(team.coverage, source_lines, details["fields"], workspace.fields)
            valid_gaps = [
                gap
                for gap in coverage.gaps
                if gap.evidence.quote in source_by_line.get(gap.evidence.line_number, "")
            ]
            workspace.coverage_gaps = valid_gaps
            workspace.coverage_status = "completed" if len(valid_gaps) == len(coverage.gaps) else "unverified"
            self._event(
                workspace,
                "coverage_agent",
                "review_coverage",
                f"全合同覆盖检查发现 {len(valid_gaps)} 个待人工核对事项；不代表内容完整性认证",
            )
        except (ModelUnavailable, ValueError) as error:
            workspace.coverage_gaps = [gap for gap in getattr(error, "partial_coverage_gaps", workspace.coverage_gaps)
                                       if gap.evidence.quote in source_by_line.get(gap.evidence.line_number, "")]
            workspace.coverage_status = (
                "skipped"
                if isinstance(error, ModelUnavailable) and error.code == "coverage_skipped"
                else "failed"
            )
            workspace.coverage_error = (
                error.public_error()
                if isinstance(error, ModelUnavailable)
                else {"message": "覆盖检查未完成", "hint": "请人工对照完整纪要。"}
            )
            self._event(
                workspace,
                "coverage_agent",
                "review_coverage",
                f"全合同覆盖检查未完成：{str(error)[:300]}；请人工对照纪要",
            )
        self.present_workspace(workspace)
        workspace.stage = "field_review"
        self._event(
            workspace,
            "extraction_agent",
            "extract_fields",
            f"本次处理 {len(target_fields)} 个字段、{len(batches)} 批；{failed_batch_count} 批未完整完成，可单独重试或人工填写",
        )
        issue_count = sum(
            bool(field.review_issues) or field.status in (FieldStatus.CONFLICT, FieldStatus.UNVERIFIED)
            for field in workspace.fields
        )
        self._event(
            workspace,
            "review_agent",
            "review_evidence",
            f"{len(batches) - failed_batch_count} 批完成独立复核，{issue_count} 项有分歧或依据问题；另有 {sum(field.status == FieldStatus.MISSING for field in workspace.fields)} 处未取得填写值（含未用表格或排版候选），需用户补充或判断留空",
        )
        finish_run(workspace)
        return self.repository.save(workspace, user_id, revision)

    def review_fields(
        self, workspace_id: str, user_id: int, revision: int, decisions: list[dict]
    ) -> ContractWorkspace:
        """保存用户的确认、修改或明确留空决定，并验证填写类型约束。

        Args:
            workspace_id: 需要校验归属的合同任务标识。
            user_id: 当前访问资源的账户标识。
            revision: 调用方持有的任务修订号。
            decisions: 用户提交的字段确认、修改或留空决定。
        """
        workspace = self._load(workspace_id, user_id, revision)
        if not workspace.fields:
            raise InvalidContractInput("请先按模板提取字段")
        details = self._template_details(workspace)
        proposed = {
            field.name: field.value for field in workspace.fields if field.status == FieldStatus.CONFIRMED
        }
        proposed.update(
            {
                decision["name"]: decision["value"].strip() if decision["action"] == "confirm" else ""
                for decision in decisions
            }
        )
        validate_slot_values(details["fields"], proposed)
        by_name = {field.name: field for field in workspace.fields}
        seen = set()
        for decision in decisions:
            name = decision["name"]
            if name not in by_name or name in seen:
                raise InvalidContractInput("审核列表包含未知或重复字段")
            seen.add(name)
            field = by_name[name]
            value = decision["value"].strip()
            note = decision.get("note", "").strip()
            if decision["action"] == "omit":
                if not note:
                    raise InvalidContractInput(f"保留空白的字段“{name}”需要填写原因")
                field.value = ""
                field.status = FieldStatus.OMITTED
            else:
                if not value:
                    raise InvalidContractInput(f"字段“{name}”不能为空，请补充或明确保留空白")
                field.value = value
                field.status = FieldStatus.CONFIRMED
            field.value_origin = "user_edit" if field.value != field.extracted_value else "user_confirmed"
            field.user_note = note
        reviewed = all(
            field.status in (FieldStatus.CONFIRMED, FieldStatus.OMITTED) for field in workspace.fields
        )
        workspace.stage = (
            "ready_to_generate"
            if reviewed
            else "field_review"
        )
        self._event(workspace, "user", "review_fields", f"保存 {len(decisions)} 个字段的人工审核")
        return self.repository.save(workspace, user_id, revision)

    def preview(self, workspace_id: str, user_id: int) -> dict:
        """只用已确认值和明确留空决定构建当前任务的文字预览。

        Args:
            workspace_id: 需要校验归属的合同任务标识。
            user_id: 当前访问资源的账户标识。
        """
        workspace = self.repository.get(workspace_id, user_id)
        self._template_details(workspace)
        values = {
            field.name: field.value for field in workspace.fields if field.status == FieldStatus.CONFIRMED
        }
        return {
            "revision": workspace.revision,
            "pending_count": sum(
                field.status not in (FieldStatus.CONFIRMED, FieldStatus.OMITTED) for field in workspace.fields
            ),
            **self.catalog.preview_contract(
                workspace.selected_template["id"],
                values,
                [field.name for field in workspace.fields if field.status == FieldStatus.OMITTED],
            ),
            "omitted_fields": [
                field.name for field in workspace.fields if field.status == FieldStatus.OMITTED
            ],
        }

    def generate(
        self,
        workspace_id: str,
        user_id: int,
        revision: int,
        preview_acknowledged: bool,
        visual_review_acknowledged: bool = False,
    ) -> ContractWorkspace:
        """校验人工审批、视觉复核和字段状态后写入合同，并原子保存文件归属。

        Args:
            workspace_id: 需要校验归属的合同任务标识。
            user_id: 当前访问资源的账户标识。
            revision: 调用方持有的任务修订号。
            preview_acknowledged: 用户是否确认已核对当前版本预览。
            visual_review_acknowledged: 用户是否单独确认已查看原件图形区域。
        """
        workspace = self._load(workspace_id, user_id, revision)
        details = self._template_details(workspace)
        if details["requires_visual_review"] and not visual_review_acknowledged:
            raise InvalidContractInput("请先人工核对图片、图形或图表区域，并明确确认这些区域无需自动填写")
        # Older all-blank reviews were saved under field_review; accept their
        # explicit decisions without requiring a fake non-empty value or re-review.
        if workspace.stage == "field_review" and workspace.fields and all(
            field.status in (FieldStatus.CONFIRMED, FieldStatus.OMITTED) for field in workspace.fields
        ):
            workspace.stage = "ready_to_generate"
        if not preview_acknowledged or workspace.stage not in ("ready_to_generate", "generated"):
            raise InvalidContractInput("请先完成所有字段审核并确认合同预览")
        if not workspace.fields or any(
            field.status not in (FieldStatus.CONFIRMED, FieldStatus.OMITTED) for field in workspace.fields
        ):
            raise InvalidContractInput("仍有未审核的字段，无法生成合同")
        values = {
            field.name: field.value for field in workspace.fields if field.status == FieldStatus.CONFIRMED
        }
        artifact = self.catalog.generate_contract(
            workspace.selected_template["id"],
            values,
            [field.name for field in workspace.fields if field.status == FieldStatus.OMITTED],
        )
        artifact.update(
            {
                "source_revision": revision,
                "created_at": utc_timestamp(),
                "reviewed_values": values,
                "visual_review_acknowledged": visual_review_acknowledged,
            }
        )
        workspace.artifacts.append(artifact)
        workspace.stage = "generated"
        self._event(
            workspace,
            "renderer",
            "generate_contract",
            f"根据审核版本 {revision} 生成合同；明确保留 {len(artifact['missing_fields'])} 个空白字段",
        )
        try:
            return self.repository.save(workspace, user_id, revision, artifact=artifact)
        except Exception:
            (self.settings.generated_dir / artifact["filename"]).unlink(missing_ok=True)
            raise
