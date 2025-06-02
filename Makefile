PHONY: *

install-docker: ; curl -fsSL get.docker.com | sh

start:          ; docker compose up
c:              ; docker compose run --entrypoint=ash svc_$(svc) # make c svc=booking
stop:           ; docker compose stop
clean:          ; docker compose down --rmi all -v --remove-orphans