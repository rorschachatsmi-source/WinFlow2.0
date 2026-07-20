#!/usr/bin/env python3
"""
flow_runner_core.py

Refactored core flow runner with logging support.
Maintains original functionality while improving code structure.
"""

import json
import os
import re
import time
import getpass
import subprocess
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass
from enum import Enum

from winflow_config import get_config


class JobStatus(Enum):
    """LSF Job status enumeration"""
    PENDING = "PEND"
    RUNNING = "RUN"
    DONE = "DONE"
    EXIT = "EXIT"
    UNKNOWN = "UNKNOWN"


@dataclass
class JobInfo:
    """Container for job information"""
    name: str
    job_id: str
    status: JobStatus
    inputs: List[str]
    outputs: List[str]


class FlowLogger:
    """Centralized logging for flow execution"""

    def __init__(self, log_file: Optional[str] = None, callback: Optional[Callable] = None):
        """
        Initialize logger
        
        Args:
            log_file: Optional file path for logging
            callback: Optional callback function for GUI integration
        """
        self.log_file = log_file
        self.callback = callback
        self.logger = self._setup_logger()

    def _setup_logger(self) -> logging.Logger:
        """Setup logging configuration"""
        logger = logging.getLogger(get_config().runner.logger_name)
        logger.setLevel(logging.DEBUG)

        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter(
            "[%(levelname)s] %(asctime)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)

        # File handler
        if self.log_file:
            os.makedirs(os.path.dirname(self.log_file) or ".", exist_ok=True)
            file_handler = logging.FileHandler(self.log_file)
            file_handler.setLevel(logging.DEBUG)
            file_formatter = logging.Formatter(
                "[%(levelname)s] %(asctime)s - %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S"
            )
            file_handler.setFormatter(file_formatter)
            logger.addHandler(file_handler)

        return logger

    def log(self, level: str, message: str):
        """Log message at specified level"""
        log_func = getattr(self.logger, level.lower(), self.logger.info)
        log_func(message)
        
        if self.callback:
            self.callback(message, level)

    def info(self, msg: str):
        self.log("INFO", msg)

    def debug(self, msg: str):
        self.log("DEBUG", msg)

    def warning(self, msg: str):
        self.log("WARNING", msg)

    def error(self, msg: str):
        self.log("ERROR", msg)


class FlowValidator:
    """Validates flow configuration and paths"""

    def __init__(self, logger: FlowLogger):
        self.logger = logger

    def validate_config(self, config: Dict) -> bool:
        """Validate flow configuration structure"""
        required_keys = ["flow_name", "stages"]
        
        for key in required_keys:
            if key not in config:
                self.logger.error(f"Missing required config key: {key}")
                return False

        if not isinstance(config["stages"], list):
            self.logger.error("'stages' must be a list")
            return False

        return True

    def validate_paths(self, paths: List[str], path_type: str = "input"):
        """Validate if paths exist"""
        for path in paths:
            if not os.path.exists(path):
                raise RuntimeError(f"Missing {path_type}: {path}")


class LSFJobManager:
    """Manages LSF job submission and monitoring"""

    def __init__(self, logger: FlowLogger, config=None):
        self.logger = logger
        self.config = config or get_config()

    def submit_job(
        self,
        job_name: str,
        command: str,
        queue: Optional[str] = None,
        cpu: Optional[int] = None,
        machine: str = "",
    ) -> str:
        """
        Submit job to LSF cluster
        
        Args:
            job_name: Unique job name
            command: Command to execute
            queue: LSF queue name
            cpu: Number of CPUs
            machine: Space-separated host list for bsub -m (optional)
            
        Returns:
            Job ID string
            
        Raises:
            RuntimeError: If job submission fails
        """
        runner_cfg = self.config.runner
        lsf_cfg = self.config.lsf
        queue = queue if queue is not None else runner_cfg.default_queue
        cpu = cpu if cpu is not None else runner_cfg.default_cpu
        log_dir = runner_cfg.job_log_dir
        os.makedirs(log_dir, exist_ok=True)

        cmd = [
            lsf_cfg.bsub,
            "-J", job_name,
            "-q", queue,
            "-n", str(cpu),
            "-o", f"{log_dir}/{job_name}.log",
            "-e", f"{log_dir}/{job_name}.err",
        ]
        machine = str(machine).strip()
        if machine:
            cmd.extend(["-m", machine])
        cmd.append(command)

        self.logger.debug(f"Submitting: {' '.join(cmd)}")

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            raise RuntimeError(f"Job submission failed: {result.stderr}")

        # Parse Job ID
        m = re.search(r"Job <(\d+)>", result.stdout)
        if not m:
            raise RuntimeError(f"Cannot parse Job ID from: {result.stdout}")

        job_id = m.group(1)
        self.logger.info(f"Job submitted: {job_name} (ID: {job_id})")
        return job_id

    def get_status(self, job_id: str) -> JobStatus:
        """Get LSF job status"""
        lsf_cfg = self.config.lsf
        bjobs_cmd = [lsf_cfg.bjobs]
        if lsf_cfg.bjobs_noheader:
            bjobs_cmd.append("-noheader")
        bjobs_cmd.extend(["-o", lsf_cfg.bjobs_output_field, str(job_id)])
        result = subprocess.run(
            bjobs_cmd,
            capture_output=True,
            text=True
        )

        status_str = result.stdout.strip()
        
        try:
            return JobStatus(status_str)
        except ValueError:
            self.logger.warning(f"Unknown job status: {status_str}")
            return JobStatus.UNKNOWN

    def wait_job(
        self,
        job_id: str,
        job_outputs: List[str],
        poll_interval: Optional[int] = None,
        validator: Optional[FlowValidator] = None,
        on_status: Optional[Callable[[JobStatus], None]] = None,
    ):
        """
        Wait for job completion and validate outputs
        
        Args:
            job_id: Job ID to monitor
            job_outputs: Expected output paths
            poll_interval: Polling interval in seconds
            validator: FlowValidator instance for output validation
            on_status: Optional callback invoked on each status poll
        """
        validator = validator or FlowValidator(self.logger)
        if poll_interval is None:
            poll_interval = self.config.runner.poll_interval

        while True:
            status = self.get_status(job_id)
            if on_status:
                on_status(status)
            self.logger.info(f"[{job_id}] Status: {status.value}")

            if status == JobStatus.DONE:
                validator.validate_paths(job_outputs, "output")
                self.logger.info(f"[{job_id}] Job completed successfully")
                return
            elif status == JobStatus.EXIT:
                raise RuntimeError(f"[{job_id}] Job exited with error")

            time.sleep(poll_interval)


class FlowRunner:
    """Main flow execution engine"""

    def __init__(
        self,
        logger: FlowLogger,
        validator: FlowValidator,
        job_manager: LSFJobManager,
        job_callback: Optional[Callable[[str, Dict], None]] = None,
    ):
        self.logger = logger
        self.validator = validator
        self.job_manager = job_manager
        self.job_callback = job_callback

    def _notify_job(self, event: str, **data):
        if self.job_callback:
            self.job_callback(event, data)

    def run_job(
        self,
        flow_name: str,
        stage_name: str,
        task_name: str,
        job: Dict,
        poll_interval: int,
        job_filter: Optional[Callable[[str], bool]] = None,
    ):
        """Execute a single job"""
        template_name = job["name"]
        job_key = f"{stage_name}/{task_name}/{template_name}"

        if job_filter and not job_filter(job_key):
            self.logger.info(f"[SKIP] {job_key} (already completed)")
            return

        job_name = self._create_unique_job_name(template_name)
        job_inputs = job["inputs"]
        job_outputs = job["outputs"]

        self._notify_job(
            "job_start",
            job_key=job_key,
            template_name=template_name,
            lsf_name=job_name,
            stage=stage_name,
            task=task_name,
            status="pending",
        )

        self.logger.info(f"[JOB] {job_name}")
        self.logger.debug(f"  Inputs: {job_inputs}")
        self.logger.debug(f"  Outputs: {job_outputs}")

        job_id = ""
        try:
            # Validate inputs
            self.validator.validate_paths(job_inputs, "input")

            # Submit job
            runner_cfg = self.job_manager.config.runner
            queue = job.get("queue") or runner_cfg.default_queue
            cpu = job.get("cpu", runner_cfg.default_cpu)
            job_id = self.job_manager.submit_job(
                job_name,
                job["command"],
                queue=queue,
                cpu=cpu,
                machine=job.get("machine", ""),
            )

            self._notify_job(
                "job_submitted",
                job_key=job_key,
                template_name=template_name,
                lsf_name=job_name,
                job_id=job_id,
                stage=stage_name,
                task=task_name,
                status=JobStatus.PENDING.value,
            )

            # Wait for completion
            self.job_manager.wait_job(
                job_id,
                job_outputs,
                poll_interval,
                self.validator,
                on_status=lambda s: self._notify_job(
                    "job_status",
                    job_key=job_key,
                    template_name=template_name,
                    lsf_name=job_name,
                    job_id=job_id,
                    status=s.value,
                ),
            )
        except Exception:
            # Cover missing inputs / submit failures too (not only wait_job).
            self._notify_job(
                "job_failed",
                job_key=job_key,
                template_name=template_name,
                lsf_name=job_name,
                job_id=job_id,
                status=JobStatus.EXIT.value,
            )
            raise

        self._notify_job(
            "job_done",
            job_key=job_key,
            template_name=template_name,
            lsf_name=job_name,
            job_id=job_id,
            status=JobStatus.DONE.value,
        )
        self.logger.info(f"[SUCCESS] {job_name}")

    def run_task(
        self,
        flow_name: str,
        stage_name: str,
        task: Dict,
        poll_interval: int,
        job_filter: Optional[Callable[[str], bool]] = None,
    ):
        """Execute a task (may contain multiple jobs)"""
        task_name = task["name"]
        self.logger.info(f"[TASK START] {task_name}")

        for job in task["jobs"]:
            self.run_job(
                flow_name, stage_name, task_name, job, poll_interval, job_filter
            )

        self.logger.info(f"[TASK END] {task_name}")

    def run_stage(
        self,
        flow_name: str,
        stage: Dict,
        poll_interval: int,
        job_filter: Optional[Callable[[str], bool]] = None,
    ):
        """Execute a stage (may contain multiple tasks in parallel)"""
        stage_name = stage["name"]
        self.logger.info(f"[STAGE START] {stage_name}")

        tasks = stage.get("tasks") or []
        if not tasks:
            self.logger.info(f"[STAGE END] {stage_name} (no tasks)")
            return

        # Submit every task immediately; surface the first failure via as_completed
        # so a sibling that dies on missing inputs is not hidden until others finish.
        with ThreadPoolExecutor(max_workers=len(tasks)) as pool:
            futures = [
                pool.submit(
                    self.run_task,
                    flow_name,
                    stage_name,
                    task,
                    poll_interval,
                    job_filter,
                )
                for task in tasks
            ]
            for future in as_completed(futures):
                future.result()

        self.logger.info(f"[STAGE END] {stage_name}")

    def run_flow(
        self,
        config: Dict,
        job_filter: Optional[Callable[[str], bool]] = None,
    ):
        """Execute complete flow"""
        if not self.validator.validate_config(config):
            raise RuntimeError("Invalid flow configuration")

        flow_name = config["flow_name"]
        poll_interval = config.get("poll_interval", self.job_manager.config.runner.poll_interval)

        self.logger.info(f"[FLOW START] {flow_name}")

        try:
            for stage in config["stages"]:
                self.run_stage(flow_name, stage, poll_interval, job_filter)

            self.logger.info(f"[FLOW SUCCESS] {flow_name}")
        except Exception as e:
            self.logger.error(f"[FLOW FAILED] {flow_name}: {str(e)}")
            raise

    @staticmethod
    def _create_unique_job_name(job_name: str) -> str:
        """Create unique job name with timestamp"""
        user = getpass.getuser()
        ts_format = get_config().lsf.job_name_timestamp_format
        ts = time.strftime(ts_format)
        return f"{user}_{job_name}_{ts}"


def create_flow_runner(
    log_file: Optional[str] = None,
    log_callback: Optional[Callable] = None,
    job_callback: Optional[Callable[[str, Dict], None]] = None,
) -> FlowRunner:
    """Factory function to create a FlowRunner instance"""
    logger = FlowLogger(log_file, log_callback)
    validator = FlowValidator(logger)
    job_manager = LSFJobManager(logger)
    return FlowRunner(logger, validator, job_manager, job_callback)


if __name__ == "__main__":
    import sys

    # Load configuration
    app_config = get_config()
    config_file = sys.argv[1] if len(sys.argv) > 1 else app_config.runner.default_flow_file

    with open(config_file, "r") as fp:
        config = json.load(fp)

    # Create and run flow
    runner = create_flow_runner(log_file=app_config.runner.session_log_file)
    runner.run_flow(config)
