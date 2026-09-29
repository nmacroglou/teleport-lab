FROM ubuntu:24.04

# Teleport agent binary, same version as the cluster.
COPY --from=public.ecr.aws/gravitational/teleport-distroless:18.11.2 /usr/local/bin/teleport /usr/local/bin/teleport

# A normal (non-root) Linux user to log in as through Teleport.
RUN useradd --create-home --shell /bin/bash labuser

ENTRYPOINT ["/usr/local/bin/teleport", "start", "--config=/etc/teleport/teleport.yaml"]
