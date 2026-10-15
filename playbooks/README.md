# Playbooks

One expert file per platform. The writing team reads the playbook for the platform it is writing for, and code checks the limits in its header.

You can edit any playbook yourself. Restart the backend after editing: a broken playbook stops startup with a clear message naming the file and the problem.

Each file needs:

- a header with `platform` (same as the file name), `label`, `max_chars`, `words: [min, max]`, `hashtags: [min, max]`, and optionally `needs_image: true/false` and `links: ok/avoid`;
- the sections `## Structure`, `## Tone`, `## Hashtags` and `## Red lines`.

Now: LinkedIn, Facebook, Instagram, X. Later phases add Upwork, Fiverr, Email and GitHub.
