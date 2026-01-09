"""
Template loader module for processing YAML service definitions.
"""

from pathlib import Path
from typing import Any, Dict, List

import yaml

from .constants import TEMPLATES_DIR


class TemplateLoader:
    """Loads and processes service templates from YAML files."""

    def __init__(self):
        self.services: Dict[str, Any] = {}
        self.categories: Dict[str, str] = {}
        self._loaded = False

    def load_template(self, template_name: str) -> str:
        """Load a template file."""
        template_path = TEMPLATES_DIR / template_name
        if not template_path.exists():
            raise FileNotFoundError(f"Template not found: {template_path}")
        return template_path.read_text(encoding="utf-8")

    def render_template(self, template: str, **kwargs) -> str:
        """Render a template with provided variables."""
        return template.format(**kwargs)

    def _load_yaml_data(self) -> None:
        """Load service definitions from YAML file."""
        if self._loaded:
            return

        yaml_path = TEMPLATES_DIR / "docker-services.yaml"
        if not yaml_path.exists():
            raise FileNotFoundError(f"Services YAML not found: {yaml_path}")

        try:
            with open(yaml_path, "r", encoding="utf-8") as file:
                data = yaml.safe_load(file)

            self.services = data.get("services", {})
            self.categories = data.get("categories", {})
            self._loaded = True

        except (yaml.YAMLError, IOError) as e:
            raise RuntimeError(f"Failed to load services YAML: {e}")

    def get_services(self) -> Dict[str, Any]:
        """Get all service definitions."""
        self._load_yaml_data()
        return self.services

    def get_categories(self) -> Dict[str, str]:
        """Get category definitions."""
        self._load_yaml_data()
        return self.categories

    def get_services_by_category(self) -> Dict[str, List[str]]:
        """Get services organized by category."""
        self._load_yaml_data()

        services_by_category = {}
        for service_id, service_data in self.services.items():
            category = service_data.get("category", "other")
            if category not in services_by_category:
                services_by_category[category] = []
            services_by_category[category].append(service_id)

        return services_by_category

    def validate_services(self) -> List[str]:
        """Validate service definitions and return list of issues."""
        self._load_yaml_data()
        issues = []

        required_fields = ["name", "description", "category", "image"]

        for service_id, service_data in self.services.items():
            for field in required_fields:
                if field not in service_data:
                    issues.append(
                        f"Service '{service_id}' missing required field: {field}"
                    )

        return issues
