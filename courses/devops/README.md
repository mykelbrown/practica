# DevOps & Platform Engineering

Part of Practica (see ../../README.md). Use `practica next` and `practica verify`.

Hands-on, terminal-driven DevOps curriculum. Progress is tracked by Practica in
`practica/progress.json`; each lesson lives in `module-XX/day-YY/` with a
`LESSON.md`, an interactive `lesson.html` (diagrams and animations),
an animated video in `media/`, a `workspace/` for your work, and a `verify.sh`
checker.

Quality gates: run `practica/tools/test-all.sh`.

| Module | Focus |
|---|---|
| 1 | Linux, terminal, Bash, networking, Git |
| 2 | Python automation, config formats, testing, linting |
| 3 | Docker, Compose, image security |
| 4 | CI/CD with GitHub Actions |
| 5 | Terraform (local providers, LocalStack/MinIO) |
| 6 | Ansible and platform engineering |
| 7 | Kubernetes (kind/k3d), Helm |
| 8 | Cloud and distributed systems (emulated AWS) |
| 9 | Observability and SRE |

Everything runs locally at no cost. Any paid or account-gated step will be
flagged as optional before it comes up.

**Cloud session note:** this container is temporary. Commit and push
`devops-lab/` and `.devops_progress.json` to a Git repository you own (or copy
them off) to keep your work between sessions.
