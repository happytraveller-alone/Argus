from fastapi import APIRouter

from app.api.v1.endpoints import projects_crud as _crud
from app.api.v1.endpoints import projects_files as _files
from app.api.v1.endpoints import projects_insights as _insights
from app.api.v1.endpoints import projects_transfer as _transfer
from app.api.v1.endpoints import projects_uploads as _uploads
from app.api.v1.endpoints.projects_shared import *

router = APIRouter()
router.include_router(_transfer.router)
router.include_router(_insights.router)
router.include_router(_uploads.router)
router.include_router(_files.router)
router.include_router(_crud.router)

create_project = _crud.create_project
read_projects = _crud.read_projects
read_project = _crud.read_project
download_project_archive = _crud.download_project_archive
get_project_info = _crud.get_project_info
update_project = _crud.update_project

export_project_bundle = _transfer.export_project_bundle
import_project_bundle = _transfer.import_project_bundle

get_stats = _insights.get_stats
get_dashboard_snapshot = _insights.get_dashboard_snapshot
get_static_scan_overview = _insights.get_static_scan_overview

get_project_files = _files.get_project_files
get_project_files_tree = _files.get_project_files_tree
get_project_file_content = _files.get_project_file_content
get_cache_stats = _files.get_cache_stats
clear_cache = _files.clear_cache
invalidate_project_cache = _files.invalidate_project_cache

generate_project_description_preview = _uploads.generate_project_description_preview
generate_project_description_for_project = _uploads.generate_project_description_for_project
create_project_with_zip = _uploads.create_project_with_zip
get_project_zip_info = _uploads.get_project_zip_info
upload_project_zip = _uploads.upload_project_zip
preview_upload_file = _uploads.preview_upload_file
upload_project_directory = _uploads.upload_project_directory
delete_project_zip_file = _uploads.delete_project_zip_file
