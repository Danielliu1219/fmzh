"""手动非功能验收；只对专用临时服务运行，自动创建合成账号，不使用真实Key。"""

import argparse
import json
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4
from datetime import date, timedelta
import httpx


def run(url, users, minutes, output, pace=5):
    run_id = uuid4().hex[:10]
    samples = []
    errors = []
    counts = Counter()
    lock = threading.Lock()
    accounts = []
    for i in range(users):
        with httpx.Client(base_url=url, timeout=10) as client:
            name = f"load_{run_id}_{i}"
            r = client.post(
                "/api/auth/register",
                json=dict(
                    username=name,
                    password="SyntheticStudy123",
                    student_no=f"L{run_id}{i}",
                ),
            )
            r.raise_for_status()
            headers = {"Authorization": "Bearer " + r.json()["access_token"]}
            r = client.post(
                "/api/exams",
                headers=headers,
                json=dict(
                    subject="合成压测科目",
                    exam_date=str(date.today() + timedelta(days=14)),
                ),
            )
            r.raise_for_status()
            eid = r.json()["id"]
            r = client.post(
                "/api/tasks",
                headers=headers,
                json=dict(
                    exam_id=eid,
                    title="压测任务",
                    plan_date=str(date.today()),
                    estimated_minutes=10,
                ),
            )
            r.raise_for_status()
            accounts.append((headers, r.json()["id"]))
    started = time.monotonic()
    deadline = started + minutes * 60
    log_stream = output.with_suffix(".requests.jsonl").open(
        "x", encoding="utf-8", buffering=1
    )

    def worker(account):
        headers, tid = account
        with httpx.Client(base_url=url, headers=headers, timeout=10) as client:
            cycle = 0
            paths = [
                "/api/dashboard",
                "/api/exams",
                "/api/focus/today",
                "/api/stats/overview?days=7",
                "/api/materials",
                "/api/features/top3",
            ]
            while time.monotonic() < deadline:
                tick = time.monotonic()
                path = paths[cycle % len(paths)]
                method = "GET"
                try:
                    if cycle % 10 == 9:
                        method = "POST" if cycle % 20 == 19 else "DELETE"
                        path = f"/api/tasks/{tid}/checkin"
                    r = client.request(method, path)
                    elapsed = time.monotonic() - tick
                    with lock:
                        samples.append(elapsed)
                        counts[r.status_code] += 1
                        log_stream.write(
                            json.dumps(
                                dict(
                                    elapsed_seconds=round(
                                        time.monotonic() - started, 3
                                    ),
                                    path=path,
                                    method=method,
                                    status=r.status_code,
                                    seconds=round(elapsed, 6),
                                )
                            )
                            + "\n"
                        )
                        if r.status_code != 200:
                            errors.append(
                                dict(
                                    path=path,
                                    status=r.status_code,
                                    request_id=r.headers.get("x-request-id"),
                                )
                            )
                except Exception as exc:
                    with lock:
                        samples.append(time.monotonic() - tick)
                        counts["transport_error"] += 1
                        errors.append(
                            dict(
                                path=path,
                                error=type(exc).__name__,
                                elapsed_seconds=round(time.monotonic() - started, 2),
                            )
                        )
                        log_stream.write(
                            json.dumps(
                                dict(
                                    path=path,
                                    error=type(exc).__name__,
                                    seconds=round(time.monotonic() - tick, 6),
                                )
                            )
                            + "\n"
                        )
                cycle += 1
                time.sleep(max(0, pace - (time.monotonic() - tick)))

    def snapshot(finished=False):
        with lock:
            ordered = sorted(samples)
            result = dict(
                users=users,
                interval_seconds=pace,
                planned_minutes=minutes,
                elapsed_seconds=round(time.monotonic() - started, 2),
                finished=finished,
                requests=len(samples),
                statuses=dict(counts),
                success_rate=counts[200] / len(samples) if samples else 0,
                error_count=len(errors),
                errors=errors[:20],
                p95_seconds=round(
                    ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))], 4
                )
                if ordered
                else None,
                max_seconds=round(max(ordered), 4) if ordered else None,
            )
        output.write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return result

    with ThreadPoolExecutor(max_workers=users) as pool:
        futures = [pool.submit(worker, a) for a in accounts]
        while not all(f.done() for f in futures):
            snapshot()
            time.sleep(5)
        for future in futures:
            future.result()
    result = snapshot(True)
    log_stream.close()
    print(json.dumps(result, ensure_ascii=False))
    # 正式NF-5.2-01：成功率至少99%、普通请求P95不超过2秒。
    if not samples or result["success_rate"] < 0.99 or result["p95_seconds"] > 2:
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--users", type=int, default=50)
    parser.add_argument("--minutes", type=float, default=60)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--pace", type=float, default=5)
    args = parser.parse_args()
    run(args.url, args.users, args.minutes, args.output, args.pace)
