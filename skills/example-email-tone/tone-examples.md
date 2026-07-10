# Tone examples (support file)

This file is not loaded automatically — the model reads it with
read_skill_file("example-email-tone", "tone-examples.md") only when it needs
concrete samples. Support files can be templates, reference docs, checklists,
or scripts (scripts are never executed from here; running anything always
goes through the run_shell plugin and its confirmation dialog).

## Too stiff → better

> Dear Sir/Madam, I am writing to inquire as to the status of my ticket.

→ "Hi — any update on ticket #4821? It's blocking our release. Thanks!"

## Too blunt → better

> Your API is broken, fix it.

→ "We're seeing 500s from /v2/users since this morning (trace attached).
Can someone take a look today? Happy to hop on a call."

## Escalation (manager cc'd)

Keep facts first, feelings out, one dated ask:
"Third follow-up on the contract review (sent May 2, May 9). We need
signature by Friday to hold the vendor's pricing. Can you confirm today?"
