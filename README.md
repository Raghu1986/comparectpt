## Docker

Build the image:

```bash
docker build -t comparectpt .
```

Run the app container:

```bash
docker run --rm -p 8000:8000 --env-file .env comparectpt
```

Open the app:

```bash
http://localhost:8000
```

## Docker Compose

Build and start the full stack:

```bash
docker compose up --build
```

Start in detached mode:

```bash
docker compose up -d --build
```

Stop the stack:

```bash
docker compose down
```

Stop the stack and remove Redis data volume:

```bash
docker compose down -v
```

## Notes

- The compose setup starts both the FastAPI app and Redis.
- In containers, `localhost` points to the container itself. If your database runs on the host machine, update `DATABASE_CONFIG` in `.env` to use `host.docker.internal` instead of `localhost`.
