#!/bin/bash
# Development helper - runs docker compose with watch mode
exec docker compose -f docker-compose.dev.yml up --watch --build "$@"
