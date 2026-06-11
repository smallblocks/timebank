DOCKER_TAG := localhost/timebank:latest
S9PK := timebank.s9pk

.PHONY: all docker javascript pack verify clean

all: pack

javascript:
	npm run build

docker:
	docker build -t $(DOCKER_TAG) .

# NOTE: icon.png — copy your app icon to assets/icon.png before packing.
# e.g., cp static/icon-512.png assets/icon.png
pack: javascript docker
	start-cli init-key 2>/dev/null || true
	start-cli s9pk pack . -o $(S9PK)

verify:
	start-cli s9pk inspect $(S9PK) manifest

clean:
	rm -rf javascript $(S9PK)
