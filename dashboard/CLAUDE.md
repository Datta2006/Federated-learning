# Claude Code project configuration

## Skill routing rules

When the user's request matches an available skill, invoke it via the
`Skill` tool. When in doubt, invoke the skill. Key routing:

- Brainstorming / product ideas → `/office-hours`
- Strategy / scope decisions → `/plan-ceo-review`
- Architecture / design review → `/plan-eng-review`
- Design system spec → `/design-consultation` or `/plan-design-review`
- QA / testing site behavior → `/qa` or `/qa-only`
- Code review / diff check → `/review`
- Ship / deploy / PR → `/ship` or `/land-and-deploy`

## Frontend workspace convention

All frontend code lives under `frontend/` within this repo. TypeScript
source is in `frontend/src`. The package manager is npm; the build command
is `npm run typecheck`, the run command is `npm run dev`.
