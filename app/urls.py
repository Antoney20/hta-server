from rest_framework.routers import DefaultRouter
from .views import (
    SelectionToolViewSet,
    SystemCategoryViewSet,
    InterventionSystemCategoryViewSet,
    InterventionScoreViewSet,
)

router = DefaultRouter()
router.register("selection-tools", SelectionToolViewSet, basename="selection-tool")
router.register("system-categories", SystemCategoryViewSet, basename="system-category")
router.register("intervention-categories", InterventionSystemCategoryViewSet, basename="intervention-category")
router.register("intervention-scores", InterventionScoreViewSet, basename="intervention-score")

urlpatterns = router.urls