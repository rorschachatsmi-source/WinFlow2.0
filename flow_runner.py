#!/usr/bin/env python3
import json
import os
import re
import time
import getpass
import subprocess
from concurrent.futures import ThreadPoolExecutor


def unique_job_name(job):
    user = getpass.getuser()
    ts = time.strftime("%Y%m%d_%H%M%S")

    return (
        f"{user}_"
        f"{job}_"
        f"{ts}"
    )


def validate_inputs(inputs):
    for path in inputs:
        if not os.path.exists(path):
            raise RuntimeError(
                f"Missing input: {path}"
            )


def submit_lsf_job(
    job_name,
    command,
    queue,
    cpu
):
    cmd = [
        "bsub",
        "-J", job_name,
        "-q", queue,
        "-n", str(cpu),
        "-o", f"log/{job_name}.log",
        "-e", f"log/{job_name}.err",
        command
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        raise RuntimeError(result.stderr)

    m = re.search(
        r"Job <(\d+)>",
        result.stdout
    )

    if not m:
        raise RuntimeError(
            f"Cannot parse Job ID\n{result.stdout}"
        )

    return m.group(1)


def get_lsf_status(job_id):
    result = subprocess.run(
        [
            "bjobs",
            "-noheader",
            "-o",
            "stat",
            str(job_id)
        ],
        capture_output=True,
        text=True
    )

    return result.stdout.strip()


def wait_job(job_id, job_output,poll_interval):
    while True:

        status = get_lsf_status(job_id)

        print(
            f"[{job_id}] {status}"
        )

        if status == "DONE" or status ==  "EXIT":
            validate_outputs(job_output)
            return


        time.sleep(poll_interval)


def validate_outputs(outputs):
    for path in outputs:
        if not os.path.exists(path):
            raise RuntimeError(
                f"Missing output: {path}"
            )


def run_job(
    flow_name,
    stage_name,
    task_name,
    job,
    poll_interval
):

    job_name = unique_job_name(job["name"])
    job_input = job["inputs"]
    job_output = job["outputs"]
    print(f"[JOB_NAME] {job_name}\n[Job Input] {job_input}\n[Job Output] {job_output}\n")
    validate_inputs(job_input)
    print(f"[SUBMIT] {job_name}")
    job_id = submit_lsf_job(
        job_name,
        job["command"],
        queue=job.get("queue", "all"),
        cpu=job.get("cpu", 1)
    )

    print(f"[JOB_ID] {job_id}")

    wait_job(
        job_id,
        job_output,
        poll_interval
    )


    print(
        f"[SUCCESS] {job_name}"
    )


def run_task(
    flow_name,
    stage_name,
    task,
    poll_interval
):
    print(
        f"[TASK START] {task['name']}"
    )

    for job in task["jobs"]:

        run_job(
            flow_name,
            stage_name,
            task["name"],
            job,
            poll_interval
        )

    print(
        f"[TASK END] {task['name']}"
    )


def run_stage(
    flow_name,
    stage,
    poll_interval
):
    print(
        f"[STAGE START] {stage['name']}"
    )

    with ThreadPoolExecutor(
        max_workers=len(stage["tasks"])
    ) as pool:

        futures = []

        for task in stage["tasks"]:

            futures.append(
                pool.submit(
                    run_task,
                    flow_name,
                    stage["name"],
                    task,
                    poll_interval
                )
            )

        for f in futures:
            f.result()

    print(
        f"[STAGE END] {stage['name']}"
    )


def run_flow(config):
    flow_name = config["flow_name"]

    poll_interval = config.get(
        "poll_interval",
        10
    )

    for stage in config["stages"]:

        run_stage(
            flow_name,
            stage,
            poll_interval
        )

    print(
        f"[FLOW SUCCESS] {flow_name}"
    )


if __name__ == "__main__":

    with open(
        "flow.json",
        "r"
    ) as fp:

        config = json.load(fp)

    run_flow(config)