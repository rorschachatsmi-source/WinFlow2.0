"""Flow document model for the visual editor."""

from __future__ import annotations

import copy
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from flow_generator.core.context import BuildContext
from flow_generator.core.models import Flow, Job, Stage, Task, make_flow, make_job, make_stage, make_task
from flow_generator.flows.apr.builder import build_apr_stage
from flow_generator.flows.pv.builder import PVFlowBuilder
from flow_generator.parsers import parse_block_stream, parse_setting_sh
from winflow_config import get_config

JobKey = str

PV_PLACEHOLDER_SETTINGS = {
    "TOP_MODULE": "",
    "MACHINE_QUEUE": "",
    "MACHINE_CPU": "4",
    "TOP_MODULE_POST": "",
    "FLAG_DMEXCL_PTN": "0",
    "FLAG_DMF": "0",
    "FLAG_DOD": "0",
    "FLAG_DEX": "0",
    "FLAG_DRC": "0",
    "FLAG_DRCBE": "0",
    "FLAG_DRCFE": "0",
    "FLAG_LVS": "0",
    "FLAG_RCXT": "0",
}

DEFAULT_QUEUE = get_config().generator.default_queue
DEFAULT_CPU = get_config().generator.default_cpu


@dataclass
class TemplateOptions:
    """User-provided options when loading a flow template."""

    queue: str = DEFAULT_QUEUE
    machine: str = ""
    cpu: int = DEFAULT_CPU
    setting_path: Optional[Path] = None
    blocks_path: Optional[Path] = None
    apr_is_current: bool = False
    apr_prefix: str = ""
    use_oasii: bool = True


def _job_key(stage: str, task: str, job_name: str) -> JobKey:
    return f"{stage}\0{task}\0{job_name}"


def _new_job_key(stage: str, task: str) -> JobKey:
    return _job_key(stage, task, f"job_{uuid.uuid4().hex[:8]}")


@dataclass
class FlowDocument:
    """Editable flow with optional canvas positions per job."""

    flow_name: str = field(default_factory=lambda: get_config().generator.blank_flow_name)
    poll_interval: int = field(default_factory=lambda: get_config().generator.poll_interval)
    stages: List[Stage] = field(default_factory=list)
    positions: Dict[JobKey, Tuple[float, float]] = field(default_factory=dict)

    def clone(self) -> "FlowDocument":
        return FlowDocument(
            flow_name=self.flow_name,
            poll_interval=self.poll_interval,
            stages=copy.deepcopy(self.stages),
            positions=dict(self.positions),
        )

    def iter_jobs(self):
        for stage in self.stages:
            for task in stage["tasks"]:
                for job in task["jobs"]:
                    yield stage["name"], task["name"], job

    def get_job(self, key: JobKey) -> Optional[Tuple[str, str, Job]]:
        stage_name, task_name, job_name = key.split("\0")
        for stage in self.stages:
            if stage["name"] != stage_name:
                continue
            for task in stage["tasks"]:
                if task["name"] != task_name:
                    continue
                for job in task["jobs"]:
                    if job["name"] == job_name:
                        return stage_name, task_name, job
        return None

    def remove_job(self, key: JobKey) -> None:
        stage_name, task_name, job_name = key.split("\0")
        for stage in self.stages:
            if stage["name"] != stage_name:
                continue
            for task in stage["tasks"]:
                if task["name"] != task_name:
                    continue
                task["jobs"] = [j for j in task["jobs"] if j["name"] != job_name]
            stage["tasks"] = [t for t in stage["tasks"] if t["jobs"]]
        self.stages = [s for s in self.stages if s["tasks"]]
        self.positions.pop(key, None)

    def add_job(
        self,
        stage_name: str,
        task_name: str,
        job: Optional[Job] = None,
        key: Optional[JobKey] = None,
    ) -> JobKey:
        if job is None:
            job = make_job(
                name=f"job_{len(self.positions) + 1}",
                command="",
                inputs=[],
                outputs=[],
                queue="",
                cpu=get_config().generator.new_job_cpu,
            )
        else:
            job = dict(job)
            job.setdefault("parents", [])
            job.setdefault("children", [])
        job_key = key or _job_key(stage_name, task_name, job["name"])

        stage = self._ensure_stage(stage_name)
        task = self._ensure_task(stage, task_name)
        task["jobs"].append(job)
        if job_key not in self.positions:
            self.positions[job_key] = auto_layout_position(self, job_key)
        return job_key

    def _ensure_stage(self, stage_name: str) -> Stage:
        for stage in self.stages:
            if stage["name"] == stage_name:
                return stage
        stage = make_stage(stage_name, [])
        self.stages.append(stage)
        return stage

    def _ensure_task(self, stage: Stage, task_name: str) -> Task:
        for task in stage["tasks"]:
            if task["name"] == task_name:
                return task
        task = make_task(task_name, [])
        stage["tasks"].append(task)
        return task

    def reorder_jobs_in_task(self, stage_name: str, task_name: str) -> None:
        keys = [
            _job_key(stage_name, task_name, job["name"])
            for stage in self.stages
            if stage["name"] == stage_name
            for task in stage["tasks"]
            if task["name"] == task_name
            for job in task["jobs"]
        ]
        if len(keys) < 2:
            return
        ordered = sorted(keys, key=lambda k: self.positions.get(k, (0, 0))[1])
        for stage in self.stages:
            if stage["name"] != stage_name:
                continue
            for task in stage["tasks"]:
                if task["name"] != task_name:
                    continue
                by_name = {job["name"]: job for job in task["jobs"]}
                task["jobs"] = [
                    by_name[key.split("\0")[2]]
                    for key in ordered
                    if key.split("\0")[2] in by_name
                ]

    def _prune_empty(self) -> None:
        for stage in self.stages:
            stage["tasks"] = [task for task in stage["tasks"] if task["jobs"]]
        self.stages = [stage for stage in self.stages if stage["tasks"]]

    def _unique_task_name(self, stage: Stage, base: str) -> str:
        existing = {task["name"] for task in stage["tasks"]}
        if base not in existing:
            return base
        index = 2
        while f"{base}_{index}" in existing:
            index += 1
        return f"{base}_{index}"

    def _relocate_key(self, old_key: JobKey, new_key: JobKey) -> None:
        if old_key == new_key:
            return
        from flow_graph import key_to_slash, rewrite_relation_key_refs

        rewrite_relation_key_refs(
            self.stages,
            key_to_slash(old_key),
            key_to_slash(new_key),
        )
        if old_key in self.positions:
            self.positions[new_key] = self.positions.pop(old_key)
        elif new_key not in self.positions:
            self.positions[new_key] = auto_layout_position(self, new_key)

    def find_job_index(self, key: JobKey) -> Optional[Tuple[Stage, Task, int]]:
        stage_name, task_name, job_name = key.split("\0")
        for stage in self.stages:
            if stage["name"] != stage_name:
                continue
            for task in stage["tasks"]:
                if task["name"] != task_name:
                    continue
                for index, job in enumerate(task["jobs"]):
                    if job["name"] == job_name:
                        return stage, task, index
        return None

    def move_job(
        self,
        key: JobKey,
        stage_name: str,
        task_name: str,
        index: Optional[int] = None,
    ) -> JobKey:
        """Move a job to another stage/task (optionally at index). Returns new key."""
        located = self.find_job_index(key)
        if not located:
            return key
        _stage, task, old_index = located
        job = task["jobs"].pop(old_index)
        self._prune_empty()

        stage = self._ensure_stage(stage_name)
        dest_task = self._ensure_task(stage, task_name)
        insert_at = len(dest_task["jobs"]) if index is None else max(0, min(index, len(dest_task["jobs"])))
        dest_task["jobs"].insert(insert_at, job)

        new_key = _job_key(stage_name, task_name, job["name"])
        self._relocate_key(key, new_key)
        if key != new_key:
            from flow_generator.gui.deps import _rewrite_dummy_paths_for_key

            _rewrite_dummy_paths_for_key(self, key, new_key)
        return new_key

    def update_job(
        self,
        key: JobKey,
        stage_name: str,
        task_name: str,
        job: Job,
    ) -> JobKey:
        """Replace a job in-place, preserving list order and canvas position."""
        old_stage, old_task, old_name = key.split("\0")
        new_key = _job_key(stage_name, task_name, job["name"])
        saved_pos = self.positions.get(key)
        remove_index: Optional[int] = None

        for stage in self.stages:
            if stage["name"] != old_stage:
                continue
            for task in stage["tasks"]:
                if task["name"] != old_task:
                    continue
                for index, existing in enumerate(task["jobs"]):
                    if existing["name"] == old_name:
                        remove_index = index
                        task["jobs"].pop(index)
                        break
            break

        self._prune_empty()

        stage = self._ensure_stage(stage_name)
        task = self._ensure_task(stage, task_name)

        if old_stage == stage_name and old_task == task_name and remove_index is not None:
            task["jobs"].insert(min(remove_index, len(task["jobs"])), job)
        else:
            task["jobs"].append(job)

        if key != new_key:
            self.positions.pop(key, None)
        if saved_pos is not None:
            self.positions[new_key] = saved_pos
        elif new_key not in self.positions:
            self.positions[new_key] = auto_layout_position(self, new_key)

        if key != new_key:
            # Keep auto dummy deps (.winflow/deps/...) aligned with the new key
            # so parent/child file links survive stage/task renames.
            from flow_generator.gui.deps import _rewrite_dummy_paths_for_key

            _rewrite_dummy_paths_for_key(self, key, new_key)

        return new_key


def ensure_unique_stage_names(document: FlowDocument) -> List[str]:
    """Rename later duplicate stage names so runner job keys stay unique.

    Runner / GUI identify jobs as ``stage/task/job``. Two stages both named
    ``a`` collide (status, edges, skip sets) and a failure in the second ``a``
    aborts the flow before later stages. Link/unlink does not intentionally
    create duplicates, but loaded JSON or repeated rename/prune cycles can.

    Later duplicates become ``a_2``, ``a_3``, … (preserving list / canvas order).
    Returns human-readable notes about renames performed.
    """
    from flow_generator.gui.deps import _rewrite_dummy_paths_for_key

    notes: List[str] = []
    seen_count: Dict[str, int] = {}
    taken = {stage["name"] for stage in document.stages}

    for stage in document.stages:
        name = stage["name"]
        seen_count[name] = seen_count.get(name, 0) + 1
        if seen_count[name] == 1:
            continue

        suffix = seen_count[name]
        new_name = f"{name}_{suffix}"
        while new_name in taken:
            suffix += 1
            new_name = f"{name}_{suffix}"
        taken.add(new_name)

        for task in stage["tasks"]:
            for job in task["jobs"]:
                old_key = _job_key(name, task["name"], job["name"])
                new_key = _job_key(new_name, task["name"], job["name"])
                document._relocate_key(old_key, new_key)
                _rewrite_dummy_paths_for_key(document, old_key, new_key)

        stage["name"] = new_name
        notes.append(f"renamed duplicate stage {name!r} → {new_name!r}")

    return notes


def reorder_document_by_canvas(document: FlowDocument) -> None:
    """Reorder stages / tasks / jobs to match the canvas layout.

    The runner executes stages in JSON list order and jobs within a task in
    list order. The editor often leaves those lists out of sync with the
    left-to-right / top-to-bottom canvas (e.g. renamed stages are appended).
    Call this before export / sync so flow.json matches what the user sees.
    """

    def _pos(stage_name: str, task_name: str, job_name: str) -> Tuple[float, float]:
        return document.positions.get(_job_key(stage_name, task_name, job_name), (0.0, 0.0))

    for stage in document.stages:
        stage_name = stage["name"]
        for task in stage["tasks"]:
            task_name = task["name"]
            task["jobs"].sort(key=lambda job: _pos(stage_name, task_name, job["name"])[1])

        def _task_y(task: Task, _sn: str = stage_name) -> float:
            ys = [_pos(_sn, task["name"], job["name"])[1] for job in task["jobs"]]
            return min(ys) if ys else 0.0

        stage["tasks"].sort(key=_task_y)

    def _stage_x(stage: Stage) -> float:
        xs = [
            _pos(stage["name"], task["name"], job["name"])[0]
            for task in stage["tasks"]
            for job in task["jobs"]
        ]
        return min(xs) if xs else 0.0

    document.stages.sort(key=_stage_x)


def document_to_flow(document: FlowDocument) -> Flow:
    ensure_unique_stage_names(document)
    reorder_document_by_canvas(document)
    # Preserve editor parents/children; do not re-seed from task-order/file.
    return make_flow(
        document.flow_name,
        copy.deepcopy(document.stages),
        document.poll_interval,
        seed_relations=False,
    )


def flow_to_document(flow: Flow) -> FlowDocument:
    from flow_graph import ensure_job_relations

    stages = copy.deepcopy(flow["stages"])
    # Keep parents/children as the editor source of truth; seed if missing.
    ensure_job_relations(stages)
    doc = FlowDocument(
        flow_name=flow["flow_name"],
        poll_interval=flow["poll_interval"],
        stages=stages,
    )
    ensure_unique_stage_names(doc)
    auto_layout_all(doc)
    return doc


def auto_layout_all(document: FlowDocument) -> None:
    from flow_generator.gui.graph import build_job_graph, layout_by_graph

    graph = build_job_graph(document)
    layout_by_graph(document, graph)


def auto_layout_position(document: FlowDocument, key: JobKey) -> Tuple[float, float]:
    stage_name, task_name, job_name = key.split("\0")
    col = 0
    for stage in document.stages:
        if stage["name"] == stage_name:
            break
        col += 1
    else:
        col = len(document.stages)

    row = 0
    for stage in document.stages:
        for task in stage["tasks"]:
            for job in task["jobs"]:
                if (
                    stage["name"] == stage_name
                    and task["name"] == task_name
                    and job["name"] == job_name
                ):
                    return (80 + col * 220, 60 + row * 90)
                if stage["name"] == stage_name:
                    row += 1
    return (80 + col * 220, 60 + row * 90)


def apply_job_resources(
    document: FlowDocument,
    queue: str = DEFAULT_QUEUE,
    machine: str = "",
    cpu: int = DEFAULT_CPU,
) -> None:
    for _stage, _task, job in document.iter_jobs():
        job["queue"] = queue
        job["cpu"] = int(cpu)
        machine = str(machine).strip()
        if machine:
            job["machine"] = machine  # type: ignore[typeddict-unknown-key]
        else:
            job.pop("machine", None)


def blank_template(options: Optional[TemplateOptions] = None) -> FlowDocument:
    opts = options or TemplateOptions()
    gen_cfg = get_config().generator
    doc = FlowDocument(
        flow_name=gen_cfg.blank_flow_name,
        poll_interval=gen_cfg.poll_interval,
        stages=[
            make_stage(
                "stage_1",
                [
                    make_task(
                        "task_1",
                        [
                            make_job(
                                "job_1",
                                "",
                                [],
                                [],
                                opts.queue,
                                opts.cpu,
                                machine=opts.machine,
                            )
                        ],
                    )
                ],
            )
        ],
    )
    auto_layout_all(doc)
    return doc


def pv_template(options: Optional[TemplateOptions] = None) -> FlowDocument:
    opts = options or TemplateOptions()
    settings = dict(PV_PLACEHOLDER_SETTINGS)
    blocks: List[Dict[str, str]] = []

    if opts.setting_path and opts.setting_path.exists():
        parsed = parse_setting_sh(opts.setting_path)
        settings.update(parsed)

    if opts.blocks_path and opts.blocks_path.exists():
        blocks = parse_block_stream(opts.blocks_path)

    build_settings = dict(settings)
    if not str(build_settings.get("TOP_MODULE", "")).strip():
        build_settings["TOP_MODULE"] = "TOP_MODULE"
    build_settings["MACHINE_QUEUE"] = opts.queue or DEFAULT_QUEUE
    build_settings["MACHINE_CPU"] = str(opts.cpu)
    build_settings["USE_OASII"] = "1" if opts.use_oasii else "0"

    context = BuildContext(
        settings=build_settings,
        blocks=blocks,
        setting_path=opts.setting_path or Path("setting.sh"),
        blocks_path=opts.blocks_path or Path("block_stream.list"),
    )

    errors = PVFlowBuilder.validate_context(context)
    if errors:
        raise ValueError("\n".join(errors))

    flow = PVFlowBuilder.build(context)
    doc = flow_to_document(flow)
    apply_job_resources(doc, opts.queue, opts.machine, opts.cpu)
    return doc


def apr_template(options: Optional[TemplateOptions] = None) -> FlowDocument:
    opts = options or TemplateOptions()
    stage = build_apr_stage(
        prefix=opts.apr_prefix,
        is_current=opts.apr_is_current,
        queue=opts.queue or DEFAULT_QUEUE,
        cpu=str(opts.cpu),
        machine=opts.machine,
    )
    apr_cfg = get_config().apr
    gen_cfg = get_config().generator
    doc = FlowDocument(
        flow_name=apr_cfg.flow_name,
        poll_interval=gen_cfg.poll_interval,
        stages=[stage],
    )
    auto_layout_all(doc)
    return doc


def apply_template(
    name: str,
    options: Optional[TemplateOptions] = None,
) -> FlowDocument:
    key = name.lower()
    opts = options or TemplateOptions()
    if key == "blank":
        return blank_template(opts)
    if key == "pv":
        return pv_template(opts)
    if key == "apr":
        return apr_template(opts)
    raise KeyError(f"Unknown template {name!r}. Available: blank, pv, apr")
