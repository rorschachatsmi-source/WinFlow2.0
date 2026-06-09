#!/usr/bin/env python3
"""
generate_flow.py

Reads:
  - setting.sh
  - block_stream.list

Generates:
  - flow.json

Supported setting format:

set TOP_MODULE = "sm8466_top"
set FLAG_DMF = "1"

Only the csh-style "set" syntax is parsed.
"""

import json
import re
from pathlib import Path

LAKER_DIR = "../LakerBZ"
GDS_DIR = "../GDS"
FLOW_DIR = "../flow"

def parse_setting_sh(path="setting.sh"):
    cfg = {}

    pattern = re.compile(
        r'^\s*set\s+(\S+)\s*=\s*"(.*)"\s*$'
    )

    with open(path) as f:
        for line in f:
            line = line.strip()

            if not line or line.startswith("#"):
                continue

            m = pattern.match(line)

            if m:
                key, value = m.groups()
                cfg[key] = value

    return cfg


def parse_block_stream(path="block_stream.list"):
    blocks = []

    p = Path(path)

    if not p.exists():
        return blocks

    with open(path) as f:
        for line in f:
            line = line.strip()

            if not line:
                continue

            if line.startswith("#"):
                continue

            parts = line.split()

            if len(parts) < 2:
                continue

            blocks.append(
                {
                    "name": parts[0],
                    "workdir": parts[1]
                }
            )

    return blocks


def make_job(name, command, inputs, outputs, queue, cpu):
    return {
        "name": name,
        "command": command,
        "queue": queue,
        "cpu": int(cpu),
        "inputs": inputs,
        "outputs": outputs
    }


def make_task(name, jobs):
    return {
        "name": name,
        "jobs": jobs
    }


def make_stage(name, tasks):
    return {
        "name": name,
        "tasks": tasks
    }


def main():
    cfg = parse_setting_sh()
    blocks = parse_block_stream()

    top = cfg["TOP_MODULE"]
    top_post = cfg.get("TOP_MODULE_POST", "").strip()

    final_top = top_post if top_post else top

    queue = cfg["MACHINE_QUEUE"]
    cpu = cfg["MACHINE_CPU"]

    flow = {
        "flow_name": "PV",
        "poll_interval": 20,
        "stages": []
    }

    dmexcl_ptn = cfg.get(
        "FLAG_DMEXCL_PTN",
        "0"
    ) == "1"

    #
    # RULE:
    #
    # FLAG_DMEXCL_PTN != 1
    #
    # streamIn_sub
    # streamIn_APR
    # streamOut_APR
    # Merge
    # streamOut_TOP
    # Verify
    #
    if not dmexcl_ptn:

        if blocks:

            tasks = []

            for b in blocks:

                jobs = [
                    make_job(
                        name=f"{b['name']}_laker",
                        command=f"{FLOW_DIR}/sub_bzgdsin_apr.sh {b['name']} {b['workdir']}",
                        inputs=[
                            f"{b['workdir']}/GDS/{b['name']}.gds.gz"
                        ],
                        outputs=[
                            f"{LAKER_DIR}/{b['name']}.blitz++",
                        ],
                        queue=queue,
                        cpu=cpu
                    )
                ]

                tasks.append(
                    make_task(
                        b["name"],
                        jobs
                    )
                )

            flow["stages"].append(
                make_stage(
                    "streamIn_sub",
                    tasks
                )
            )

        flow["stages"].append(
            make_stage(
                "streamIn_APR",
                [
                    make_task(
                        f"{top}_streamIn_APR",
                        [
                            make_job(
                                name=f"{top}_laker_In",
                                command=f"{FLOW_DIR}/bzgdsin_apr.sh",
                                inputs=["../DATA/apr.gds.gz"],
                                outputs=[
                                    f"{LAKER_DIR}/{top}_APR.blitz++",
                                ],
                                queue=queue,
                                cpu=cpu
                            )
                        ]
                    )
                ]
            )
        )

        flow["stages"].append(
            make_stage(
                "streamOut_APR",
                [
                    make_task(
                        f"{top}_streamOut_APR",
                        [
                            make_job(
                                name=f"{top}_laker_Out",
                                command=f"{FLOW_DIR}/bzgdsout_apr.sh",
                                inputs=[
                                    f"{LAKER_DIR}/{top}_APR.blitz++"
                                ],
                                outputs=[
                                    f"{GDS_DIR}/{top}_FULL.gds.gz"
                                ],
                                queue=queue,
                                cpu=cpu
                            )
                        ]
                    )
                ]
            )
        )

    #
    # RULE:
    #
    # FLAG_DMEXCL_PTN == 1
    #
    # streamIn_sub_dummy
    # streamOut_APR
    # streamIn_APR
    # Merge
    # streamOut_TOP
    # Verify
    #
    else:

        if not blocks:
            raise SystemExit(
                "ERROR: FLAG_DMEXCL_PTN=1 requires non-empty block_stream.list"
            )

        tasks = []

        for b in blocks:

            jobs = [
                make_job(
                    name=f"{b['name']}_calibre",
                    command=f"{FLOW_DIR}/sub_calibre_dm.sh {b['name']} {b['workdir']}",
                    inputs=[f"{LAKER_DIR}/sub_dmexcl.calibre"],
                    outputs=[
                        f"{LAKER_DIR}/{b['name']}_dummy.gds.gz"
                    ],
                    queue=queue,
                    cpu=cpu
                ),
                make_job(
                    name=f"{b['name']}_laker",
                    command=f'{FLOW_DIR}/sub_bzgdsin_apr.sh {b["name"]} dummy',
                    inputs=[
                        f"{LAKER_DIR}/{b['name']}_dummy.gds.gz"
                    ],
                    outputs=[
                        f"{LAKER_DIR}/{b['name']}.blitz++",
                    ],
                    queue=queue,
                    cpu=cpu
                )
            ]

            tasks.append(
                make_task(
                    f"{b['name']}_dummy",
                    jobs
                )
            )

        flow["stages"].append(
            make_stage(
                "streamIn_sub_dummy",
                tasks
            )
        )

        flow["stages"].append(
            make_stage(
                "streamOut_APR",
                [
                    make_task(
                        f"{top}_streamOut_APR",
                        [
                            make_job(
                                name=f"{top}_laker_Out",
                                command=f"{FLOW_DIR}/bzgdsout_apr.sh",
                                inputs=[
                                    f"{LAKER_DIR}/{top}_APR.blitz++"
                                ],
                                outputs=[
                                    f"{GDS_DIR}/{top}_FULL.gds.gz"
                                ],
                                queue=queue,
                                cpu=cpu
                            )
                        ]
                    )
                ]
            )
        )

        flow["stages"].append(
            make_stage(
                "streamIn_APR",
                [
                    make_task(
                        f"{top}_streamIn_APR",
                        [
                            make_job(
                                name=f"{top}_laker_In",
                                command=f"{FLOW_DIR}/bzgdsin_apr.sh",
                                inputs=["../DATA/apr.gds.gz"],
                                outputs=[
                                    f"{LAKER_DIR}/{top}_APR.blitz++",
                                ],
                                queue=queue,
                                cpu=cpu
                            )
                        ]
                    )
                ]
            )
        )

    merge_tasks = []

    mapping = [
        ("FLAG_DMF", "dmf", "DM"),
        ("FLAG_DOD", "dod", "DODPO"),
        ("FLAG_DEX", "dex", "DMEXCL"),
    ]

    for flag, script, tag in mapping:

        if cfg.get(flag, "0") == "1":
            if tag == "DMEXCL":
                outputs =  [f"{GDS_DIR}/{tag}.gds.gz"]
            else:
                outputs =  [f"{GDS_DIR}/{tag}.gds"]
            merge_tasks.append(
                make_task(
                    tag,
                    [
                        make_job(
                            f"Calibre_{script}",
                            f"{FLOW_DIR}/{script}.sh",
                            [f"{GDS_DIR}/{top}_FULL.gds.gz"],
                            outputs,
                            queue,
                            cpu
                        ),
                        make_job(
                            f"laker_{script}",
                            f"{FLOW_DIR}/bzgdsin_{script}.sh",
                            outputs,
                            [f"{LAKER_DIR}/{top}_{tag}.blitz++"],
                            queue,
                            cpu
                        )
                    ]
                )
            )

    merge_tasks.append(
        make_task(
            "laker_text",
            [
                make_job(
                    "laker_text",
                    f"{FLOW_DIR}/laker_text.sh",
                    [f"{LAKER_DIR}/{top}_APR.blitz++"],
                    [f"{LAKER_DIR}/create_text_from_APRgds.tcl"],
                    queue,
                    cpu
                )
            ]
        )
    )

    flow["stages"].append(
        make_stage("Merge", merge_tasks)
    )

    flow["stages"].append(
        make_stage(
            "streamOut_TOP",
            [
                make_task(
                    f"{top}_streamOut_TOP",
                    [
                        make_job(
                            "laker_topLib",
                            f"{FLOW_DIR}/laker_topLib.sh",
                            ["laker_topLib.tcl",f"{LAKER_DIR}/create_text_from_APRgds.tcl"],
                            [f"{LAKER_DIR}/{final_top}_LIB.blitz++"],
                            queue,
                            cpu
                        ),
                        make_job(
                            f"{top}_Out",
                            f"{FLOW_DIR}/bzgdsout_top.sh",
                            [f"{LAKER_DIR}/{final_top}_LIB.blitz++",f"{GDS_DIR}/{top}_FULL.gds.gz"],
                            [f"{GDS_DIR}/{final_top}.gds.gz"],
                            queue,
                            cpu
                        ),
                        make_job(
                            "gds2oas",
                            f"{FLOW_DIR}/gds2oas.sh",
                            [f"{GDS_DIR}/{final_top}.gds.gz"],
                            [f"{GDS_DIR}/{final_top}.oas"],
                            queue,
                            cpu
                        )
                    ]
                )
            ]
        )
    )

    verify_tasks = []

    if cfg.get("FLAG_DRCBE", "0") == "1":
        verify_tasks.append(
            make_task(
                "DRCBE",
                [
                    make_job(
                        "DRCBE",
                        f"{FLOW_DIR}/run_drc",
                        [f"{GDS_DIR}/{final_top}.oas"],
                        ["DRC.rep"],
                        queue,
                        cpu
                    )
                ]
            )
        )

    if cfg.get("FLAG_DRCFE", "0") == "1":
        verify_tasks.append(
            make_task(
                "DRCFE",
                [
                    make_job(
                        "DRCFE",
                        f"{FLOW_DIR}/run_drc",
                        [f"{GDS_DIR}/{final_top}.oas"],
                        ["DRC.rep"],
                        queue,
                        cpu
                    )
                ]
            )
        )

    if verify_tasks:
        flow["stages"].append(
            make_stage(
                "Verify",
                verify_tasks
            )
        )

    with open("flow.json", "w") as fp:
        json.dump(
            flow,
            fp,
            indent=2
        )

    print("Generated flow.json")


if __name__ == "__main__":
    main()