---
description: "Start new work from a request or a specification document: intake, quick code probe, the size decision (one feature or a group of features), and L0-L3 routing."
argument-hint: "<feature request | path to a specification document>"
disable-model-invocation: true
---

Follow the human-rights workflow skill at `${CLAUDE_PLUGIN_ROOT}/skills/human-rights/SKILL.md` (read it first if it is not loaded in this conversation).

Start a new feature (§3 of the skill) for this request:

$ARGUMENTS

If the request is empty, ask what to build. If it names a document, read the document first: it is the
request. Decide the size before anything else (`references/splitting.md`); a document or a broad request is
usually compound and becomes a group.
