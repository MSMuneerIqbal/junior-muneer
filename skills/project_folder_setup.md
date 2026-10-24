---
name: project_folder_setup
description: Set up a simple project folder and starter notes in a location chosen by the user. Use for a new client or personal project, with existing files preserved.
for: [junior_muneer, computer_agent]
---
## Steps
1. Get the exact parent folder, project name and project purpose from the user. Ask for the location if missing. Junior passes the request and skill name to the Computer Agent for changes.
2. Inspect the parent with pc_list. Check whether the project already exists; never replace an existing project or assume a similarly named folder is the intended target.
3. Propose a minimal structure appropriate to the request, usually notes, assets and deliverables with a short README.md. If the user specifies a structure, use it instead. Include only supplied project facts in the README.
4. Use pc_make_folder and pc_write under normal permission rules. Create parents before children. If a prerequisite is awaiting approval, explain the next step and wait; do not claim the whole structure is ready.
5. Check executed results with pc_list/pc_read, preserving all pre-existing files. Report the root path, what was created, and any remaining cards.

## Result
A small folder structure and useful starter notes, with verified paths. Clearly distinguish the proposed structure from what exists now.

## Boundaries
This is folder setup, not software installation or deployment. Do not install packages, initialize Git, run commands, change permissions, save secrets, or upload anything unless separately requested and allowed. Never bypass a refusal or overwrite existing files.
