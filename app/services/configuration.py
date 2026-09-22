from app.configuration_repository import ConfigurationRepository
from app.models import ConfigurationDocument, ConfigurationImportResult


class ConfigurationService:
    def __init__(self, repository: ConfigurationRepository) -> None:
        self._repository = repository

    def export(self) -> ConfigurationDocument:
        return self._repository.export()

    def import_document(
        self,
        document: ConfigurationDocument,
        *,
        dry_run: bool = False,
    ) -> ConfigurationImportResult:
        runtime_states_reset = (
            0 if dry_run else self._repository.replace(document)
        )
        return ConfigurationImportResult(
            projects_imported=len(document.projects),
            rules_imported=len(document.rules),
            runtime_states_reset=runtime_states_reset,
            dry_run=dry_run,
        )
