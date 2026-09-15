# Working agreements

- Use `.venv/Scripts/python.exe` for every project Python command on Windows. Install project Python dependencies only in `.venv`.
- Do not add co-author trailers, AI attribution, or assistant watermarks to commit messages. Disclose AI tools used in the README instead.
- Commit coherent implementation milestones after relevant checks. Do not defer all history to the end of a piece of work.
- Present unresolved product, architecture, and audit-method decisions with alternatives and reasons. The user makes the final choice. Do not treat recommendations in planning notes as approved decisions.
- Ask about material gaps in the instructions. Explain what is known, what is missing, and where the ambiguity arose.
- Give manual GitHub, hosting, or account setup instructions one step at a time. Wait for the user's result before the next manual step.
- Keep code and rationale understandable for the user's detailed review. Do not require a review after every edit.
- Real client documents, extracted text, client-derived results, and private planning notes stay out of Git. Any deployed instance must protect its data with access controls.
- Do not commit secrets or virtual environments.
- Budget: use free resources only. Do not activate paid plans or paid fallback APIs without a new user instruction.
- The user performs account setup, settings changes, and browser navigation manually. Give exactly one actionable step at a time and wait for its result. Do not use browser automation for these activities unless the user changes this preference.
