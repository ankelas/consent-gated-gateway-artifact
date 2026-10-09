"""Redelivery test: one consent event must produce one partner-side effect.

The consent experiment shows that nothing reaches a partner before the user
consents. This test adds the second half of the invariant: after consent, the
same event id delivered twice must still produce a single recorded partner
action, because the gateway stores the event-level response and replays it
instead of starting a second task.

Only partner-side effect records are read; no outbound message is produced.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import photon_cells  # noqa: E402
from consent_execution import AIC_PREFIX, count_since, first_aic  # noqa: E402
from photon_cells import Injector, internal_token  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trials", type=int, default=10)
    parser.add_argument("--settle", type=float, default=20.0,
                        help="seconds to let the consented call land before redelivery")
    parser.add_argument("--window", type=float, default=20.0,
                        help="seconds to observe after the redelivery")
    parser.add_argument("--adapter", default=None)
    parser.add_argument("--token", default=None)
    parser.add_argument("--effect-log", required=True)
    parser.add_argument("--samples", type=Path, default=Path("data/live_direct_samples_v2.jsonl"))
    parser.add_argument("--out", type=Path, default=Path("data/live_consent_redelivery.jsonl"))
    args = parser.parse_args()

    samples = [json.loads(line) for line in args.samples.read_text(encoding="utf-8").splitlines() if line.strip()]
    injector = Injector(args.token or internal_token())
    if args.adapter:
        photon_cells.ADAPTER = args.adapter
    args.out.parent.mkdir(parents=True, exist_ok=True)

    with args.out.open("w", encoding="utf-8") as handle:
        for index in range(args.trials):
            sample = samples[index % len(samples)]
            stamp = int(time.time() * 1000)
            caller = f"+88{9000 + index:08d}"
            chat = f"iMessage;-;{caller}-{stamp}"

            start = dt.datetime.now(dt.timezone.utc)
            first = injector.send(f"rd-{stamp}-a", caller, chat, sample["text"])
            reply1 = " ".join(str(item) for item in first["replies"])
            candidate = first_aic(reply1)
            mine = bool(candidate and candidate.startswith(AIC_PREFIX))

            consent_text = f"使用 1：{sample['text']}"
            consent_id = f"rd-{stamp}-b"
            injector.send(consent_id, caller, chat, consent_text)
            time.sleep(args.settle)
            after_consent = count_since(start, args.effect_log)

            redeliver_mark = dt.datetime.now(dt.timezone.utc)
            replays = []
            for attempt in range(2):
                replay = injector.send(consent_id, caller, chat, consent_text)
                replays.append(" ".join(str(item) for item in replay["replies"])[:200])
            time.sleep(args.window)
            after_replay = count_since(redeliver_mark, args.effect_log)

            row = {
                "trial": index,
                "sample": sample["sample_id"],
                "first_candidate_is_study_partner": mine,
                "effects_after_consent": sum(after_consent.values()),
                "effects_from_redelivery": sum(after_replay.values()),
                "replay_replies": replays,
            }
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            handle.flush()
            print(f"[{index + 1}/{args.trials}] mine={mine} after_consent={row['effects_after_consent']} "
                  f"from_redelivery={row['effects_from_redelivery']}", flush=True)
    print(f"wrote {args.trials} trials to {args.out}")


if __name__ == "__main__":
    main()
