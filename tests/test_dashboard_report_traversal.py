# -*- coding: utf-8 -*-
from pathlib import Path
import pytest
from dashboard.backend.report_generator import ReportGenerator


def test_generate_report_refuse_traversal_et_format_invalide(tmp_path):
    db_file = tmp_path / "data" / "bots.db"
    db_file.parent.mkdir(parents=True, exist_ok=True)
    db_file.touch()

    generator = ReportGenerator(str(db_file))

    # Vérifier l'état initial des fichiers créés sous tmp_path
    fichiers_avant = set(tmp_path.rglob("*"))

    with pytest.raises(ValueError, match="invalide"):
        generator.generate(scope="../../x")

    with pytest.raises(ValueError, match="invalide"):
        generator.generate(format="bat")

    fichiers_apres = set(tmp_path.rglob("*"))
    assert fichiers_avant == fichiers_apres, f"Des fichiers ont été créés : {fichiers_apres - fichiers_avant}"
