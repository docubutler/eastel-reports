# PostgreSQL To Mongo Request Sync

This folder contains the standalone request-log sync flow from PostgreSQL to MongoDB.

## Files

- `config-sample.yml`
- local `config.yml`
- `requirements.txt`
- `create_mongo_request_log_collection.py`
- `postgres_to_mongo_request_log_sync.py`
- `drop_request_log_reporting_indexes.py`
- `recreate_request_log_reporting_indexes.py`
- `release_request_log_sync_lock.py`
- `test_postgres_connection.py`
- `test_mongo_connection.py`

## Config

Copy the sample file before running:

```powershell
Copy-Item config-sample.yml config.yml
```

The local `config.yml` contains:

- PostgreSQL connection settings
- MongoDB URI, database, request collection, and state collection
- request source table and sync tuning values

## Run

### Foreground (with console output)
```powershell
python create_mongo_request_log_collection.py
python postgres_to_mongo_request_log_sync.py
```

### Background (Linux)

#### Option 1: Using nohup

Run the sync in the background with logs written to file only:

```bash
nohup python postgres_to_mongo_request_log_sync.py > /dev/null 2>&1 &
```

To check if the process is running:
```bash
ps aux | grep postgres_to_mongo_request_log_sync
```

To stop the process:
```bash
pkill -f postgres_to_mongo_request_log_sync
```

#### Option 2: Using tmux

Start a detached tmux session:

```bash
tmux new-session -d -s postgres-request-sync python postgres_to_mongo_request_log_sync.py
```

View the session:
```bash
tmux attach-session -t postgres-request-sync
```

Stop the session:
```bash
tmux kill-session -t postgres-request-sync
```

#### Option 3: Using systemd service (Recommended for production)

Create a systemd service file at `/etc/systemd/system/postgres-to-mongo-request-sync.service`:

```ini
[Unit]
Description=PostgreSQL to MongoDB Request Log Sync
After=network.target

[Service]
Type=simple
User=your_user
WorkingDirectory=/path/to/postgres-to-mongo-request-sync
ExecStart=/usr/bin/python3 postgres_to_mongo_request_log_sync.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

Replace:
- `your_user` with your actual username
- `/path/to/postgres-to-mongo-request-sync` with the absolute path to the script directory

Then enable and start the service:

```bash
sudo systemctl daemon-reload
sudo systemctl start postgres-to-mongo-request-sync
sudo systemctl enable postgres-to-mongo-request-sync
```

Monitor the service:
```bash
sudo systemctl status postgres-to-mongo-request-sync
sudo journalctl -u postgres-to-mongo-request-sync -f
```

Stop the service:
```bash
sudo systemctl stop postgres-to-mongo-request-sync
```
