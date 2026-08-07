# Shell helpers for the production Docker Compose deployment.
alias phone_start='docker compose --project-directory /opt/apps/phone-voice-insight --env-file /opt/apps/phone-voice-insight/.env -f /opt/apps/phone-voice-insight/docker-compose.prod.yml up -d'
alias phone_stop='docker compose --project-directory /opt/apps/phone-voice-insight --env-file /opt/apps/phone-voice-insight/.env -f /opt/apps/phone-voice-insight/docker-compose.prod.yml stop'
alias phone_restart='docker compose --project-directory /opt/apps/phone-voice-insight --env-file /opt/apps/phone-voice-insight/.env -f /opt/apps/phone-voice-insight/docker-compose.prod.yml restart'
