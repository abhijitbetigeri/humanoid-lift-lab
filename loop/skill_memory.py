"""Validated development-only skill memory. No model calls or automatic promotion.

The host owns validation manifests; model-written declarations are not evidence.
See docs/skill-memory.md for the trust boundary and evaluation protocol.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import tempfile


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def environment_hash(paths):
    """Hash named environment files; pass stable project-relative names as keys."""
    hashes = {name: file_hash(path) for name, path in sorted(paths.items())}
    return hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()


def _tokens(text):
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def _artifact(path):
    p = Path(path).resolve()
    return {"path": str(p), "sha256": file_hash(p)}


def _verify(record):
    for artifact in record["artifacts"].values():
        if file_hash(artifact["path"]) != artifact["sha256"]:
            raise ValueError("memory evidence changed: " + artifact["path"])


class SkillMemory:
    """JSON store with explicit admission, provenance validation and bounded retrieval."""

    def __init__(self, path):
        self.path = Path(path)

    def _load(self):
        if not self.path.exists():
            return []
        data = json.loads(self.path.read_text())
        if data.get("version") != 1:
            raise ValueError("unsupported memory version")
        return data["skills"]

    def admit(self, *, title, guidance, tags, controller_path, config_path,
              validation_path, environment_files):
        """Admit a host-validated skill; validation schema is documented separately.

        Validation must reference the exact controller/environment and successful
        real-simulator development trials. A critic response is never accepted.
        """
        if not title.strip() or not guidance.strip() or not tags:
            raise ValueError("title, guidance and tags are required")
        if len(title) > 160 or len(guidance) > 4000:
            raise ValueError("skill text exceeds limits")
        if not environment_files:
            raise ValueError("environment files are required")
        config = json.loads(Path(config_path).read_text())
        validation = json.loads(Path(validation_path).read_text())
        if config.get("stub") is not False or config.get("split") != "development":
            raise ValueError("only explicitly non-stub development runs are admissible")
        if validation.get("backend") != "sim.trial" or validation.get("split") != "development":
            raise ValueError("validation must use real development simulation")
        if validation.get("validator") != "independent-physics-scorer":
            raise ValueError("independent physics validation is required")
        ctrl_hash = file_hash(controller_path)
        env_hash = environment_hash(environment_files)
        if validation.get("controller_sha256") != ctrl_hash or validation.get("environment_sha256") != env_hash:
            raise ValueError("validation provenance does not match controller/environment")
        trials = validation.get("trials", [])
        if not trials:
            raise ValueError("successful validation trials are required")
        artifacts = {"controller": _artifact(controller_path), "config": _artifact(config_path),
                     "validation": _artifact(validation_path)}
        for name, path in sorted(environment_files.items()):
            artifacts["environment:" + name] = _artifact(path)
        base = Path(validation_path).resolve().parent
        for i, trial in enumerate(trials):
            result_path = base / trial["result_path"]
            trajectory_path = base / trial["trajectory_path"]
            if file_hash(result_path) != trial.get("result_sha256") or file_hash(trajectory_path) != trial.get("trajectory_sha256"):
                raise ValueError("trial evidence hash mismatch")
            result = json.loads(result_path.read_text())
            if result.get("success") is not True or result.get("fail_reason") is not None:
                raise ValueError("failed trials cannot validate a skill")
            artifacts[f"result:{i}"] = _artifact(result_path)
            artifacts[f"trajectory:{i}"] = _artifact(trajectory_path)
        record = {"title": title.strip(), "guidance": guidance.strip(), "tags": sorted(set(tags)),
                  "controller_sha256": ctrl_hash, "environment_sha256": env_hash,
                  "split": "development", "artifacts": artifacts}
        record["id"] = hashlib.sha256(json.dumps(record, sort_keys=True).encode()).hexdigest()[:24]
        skills = self._load()
        if not any(s["id"] == record["id"] for s in skills):
            skills.append(record)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd, temp = tempfile.mkstemp(dir=self.path.parent, prefix=".memory-", suffix=".json")
            try:
                with os.fdopen(fd, "w") as f:
                    json.dump({"version": 1, "skills": skills}, f, indent=2, sort_keys=True)
                os.replace(temp, self.path)
            finally:
                if os.path.exists(temp):
                    os.unlink(temp)
        return record["id"]

    def retrieve(self, query, *, environment_sha256, enabled=False, limit=3, max_chars=3000):
        """No memory unless enabled. Only matching, unchanged development evidence.

        A frozen copy of this store must be used during held-out evaluation.
        This method never learns from the query or writes to the store.
        """
        if not enabled or limit <= 0 or max_chars <= 0:
            return ""
        words = _tokens(query)
        ranked = []
        for skill in self._load():
            if skill.get("split") != "development" or skill["environment_sha256"] != environment_sha256:
                continue
            _verify(skill)
            relevance = len(words & _tokens(skill["title"] + " " + " ".join(skill["tags"])))
            if relevance:
                ranked.append((-relevance, skill["id"], skill))
        blocks = []
        for _, _, skill in sorted(ranked)[:limit]:
            block = f"Validated development skill [{skill['id']}]: {skill['title']}\n{skill['guidance']}"
            candidate = "\n\n".join(blocks + [block])
            if len(candidate) <= max_chars:
                blocks.append(block)
        return "\n\n".join(blocks)
