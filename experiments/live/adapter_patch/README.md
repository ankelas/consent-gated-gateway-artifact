# Adapter change that wires the advisory judgment plane in

Files: src/imessage_adapter/{judgment.py,agent.py,config.py}, docker-compose.yml

## agent.py (hook inside photon_message, helper appended after it)
        # The key-based store answers replays of the same event. A rewritten
        # request is not the same key, so the gateway consults the judgment
        # plane for that direction; in advise mode the verdict is recorded and
        # the execution path below is untouched.
        if self.judgment.enabled:
            await self._advise_replay(caller_id, chat_guid, message_id, text)

    async def _advise_replay(self, caller_id: str, chat_guid: str, message_id: str, text: str) -> None:
        """Consult J5 and log the verdict; never changes an execution decision."""
        try:
            history = self.store.history(caller_id, chat_guid, self.settings.llm_max_history_messages)
            prior = [item["content"] for item in history if item.get("role") == "user"]
            verdict = await self.judgment.judge(text, prior)
        except Exception as error:  # noqa: BLE001 - advisory only
            verdict = {"point": "J5", "label": "error", "branch": "proceed",
                       "error": f"{type(error).__name__}: {error}"[:160]}
        verdict.update({"caller_id": caller_id, "chat_guid": chat_guid,
                        "message_id": message_id, "at": time()})
        self.judgment.log(verdict)
## config.py (new settings)
42:    judgment_mode: str
43:    judgment_threshold: float
44:    judgment_log_path: str
101:            judgment_mode=os.getenv("JUDGMENT_MODE", "off"),
102:            judgment_threshold=float(os.getenv("JUDGMENT_THRESHOLD", "0.9")),
103:            judgment_log_path=os.getenv("JUDGMENT_LOG", "/data/imessage/state/judgment_log.jsonl"),

## docker-compose.yml (new environment)
12:      JUDGMENT_MODE: ${JUDGMENT_MODE:-advise}
13:      JUDGMENT_THRESHOLD: ${JUDGMENT_THRESHOLD:-0.9}
14:      JUDGMENT_LOG: /data/imessage/state/judgment_log.jsonl
