# Docker conventions

Application images use multi-stage builds and run as a non-root user. Development
targets retain the tools needed for live reload and migration commands; production
targets contain only runtime dependencies and the built frontend assets.

Do not add credentials to Dockerfiles, image layers, Compose files, or build args.
Supply them at runtime through the local ignored `.env` file or the target platform's
secret manager.
