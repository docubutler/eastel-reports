from pathlib import Path

import yaml

from hlr_reconciliation.config import load_config, validate_config


def test_load_config_expands_environment_values(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MONGO_URI", "mongodb://example")
    config_path = tmp_path / "config.yml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "general": {
                    "application_name": "HLR",
                    "version": "1",
                    "environment": "test",
                    "timezone": "UTC",
                },
                "scheduler": {},
                "transfer": {"protocol": "local", "local_source_file": "sample.tar.gz"},
                "hlr": {"required_headers": ["IMSI", "MSISDN", "IMEISV"]},
                "boss": {"sql_query": "select msisdn, imsi from boss"},
                "iot": {"sql_query": "select msisdn, imsi from iot"},
                "mongo": {"uri": "${MONGO_URI}", "database": "db", "collections": {}},
                "reporting": {"output_columns": ["MSISDN", "IMSI", "inBSS", "inCRM", "inHLR"]},
                "email": {"enabled": False},
                "logging": {},
            }
        ),
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.mongo.uri == "mongodb://example"
    assert config.transfer.local_source_file == tmp_path / "sample.tar.gz"
    validate_config(config, require_runtime_secrets=False)
