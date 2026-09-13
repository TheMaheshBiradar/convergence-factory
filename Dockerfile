# Reproducible delivery image. Analytical core is stdlib-only; the pinned
# constraints add the AST/SQL probe backends so every partner runs an identical
# stack. Build:  docker build -t convergence-factory .
FROM python:3.11-slim

WORKDIR /app

# Dependencies first (better layer caching)
COPY constraints.txt ./
RUN pip install --no-cache-dir -r constraints.txt

# The package
COPY pyproject.toml README.md ./
COPY src ./src
COPY fixtures ./fixtures
RUN pip install --no-cache-dir .

ENV PYTHONPATH=/app/src
# Mount a repo directory at /repos and an output dir at /out:
#   docker run --rm -v "$PWD/repos:/repos" -v "$PWD/out:/out" convergence-factory \
#     matrix /repos --out /out
ENTRYPOINT ["python", "-m", "convergence_factory.pipeline"]
CMD ["/app/fixtures/repos", "--out", "/out"]
