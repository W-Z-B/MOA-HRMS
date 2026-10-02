"""Installs HrmsAdminSite as the default admin site. Kept apart from admin_site.py because this module is
imported while INSTALLED_APPS is read, before any model can be imported."""

from django.contrib.admin.apps import AdminConfig


class HrmsAdminConfig(AdminConfig):
    default_site = "iam.admin_site.HrmsAdminSite"
