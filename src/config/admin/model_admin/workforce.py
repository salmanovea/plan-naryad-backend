from src.config.admin.categories import CATEGORY_WORKFORCE
from src.config.admin.model_admin.base_admin import BaseAdmin
from src.models.dbo.tables.workforce import ArticleBDR, ArticleBDRWork


class ArticleBDRAdmin(BaseAdmin, model=ArticleBDR):  # type: ignore[call-arg]
    category = CATEGORY_WORKFORCE
    name = "Статья БДР"
    name_plural = "Статьи БДР"
    icon = "fa-solid fa-file-invoice"

    column_list = [
        ArticleBDR.id,
        ArticleBDR.code_1c,
        ArticleBDR.name,
    ]
    column_details_list = [
        ArticleBDR.id,
        ArticleBDR.code_1c,
        ArticleBDR.name,
    ]
    form_columns = [
        ArticleBDR.code_1c,
        ArticleBDR.name,
    ]
    column_searchable_list = [ArticleBDR.code_1c, ArticleBDR.name]
    column_sortable_list = [ArticleBDR.code_1c, ArticleBDR.name]


class ArticleBDRWorkAdmin(BaseAdmin, model=ArticleBDRWork):  # type: ignore[call-arg]
    category = CATEGORY_WORKFORCE
    name = "Привязка статьи к работе"
    name_plural = "Привязки статей к работам"
    icon = "fa-solid fa-link"

    column_list = [
        ArticleBDRWork.id,
        ArticleBDRWork.article_bdr_id,
        ArticleBDRWork.work_id,
    ]
    column_details_list = [
        ArticleBDRWork.id,
        ArticleBDRWork.article_bdr,
        ArticleBDRWork.work,
    ]
    form_columns = [
        ArticleBDRWork.article_bdr,
        ArticleBDRWork.work,
    ]
