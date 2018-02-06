# -*- coding: utf-8 -*-
#

from rest_framework import generics
from rest_framework.response import Response
from rest_framework_bulk import BulkModelViewSet
from rest_framework_bulk import ListBulkCreateUpdateDestroyAPIView
from rest_framework.pagination import LimitOffsetPagination
from django.shortcuts import get_object_or_404
from django.db.models import Q

from common.mixins import IDInFilterMixin
from common.utils import get_logger
from ..hands import IsSuperUser, IsValidUser, IsSuperUserOrAppUser, \
    get_user_granted_assets
from ..models import  Asset, SystemUser, AdminUser, Node
from .. import serializers
from ..tasks import update_asset_hardware_info_manual, \
    test_asset_connectability_manual
from ..utils import LabelFilter


logger = get_logger(__file__)
__all__ = [
    'AssetViewSet', 'UserAssetListView', 'AssetListUpdateApi',
    'AssetRefreshHardwareApi', 'AssetAdminUserTestApi'
]


class AssetViewSet(IDInFilterMixin, LabelFilter, BulkModelViewSet):
    """
    API endpoint that allows Asset to be viewed or edited.
    """
    filter_fields = ("hostname", "ip")
    search_fields = filter_fields
    ordering_fields = ("hostname", "ip", "port", "cluster", "cpu_cores")
    queryset = Asset.objects.all()
    serializer_class = serializers.AssetSerializer
    pagination_class = LimitOffsetPagination
    permission_classes = (IsSuperUserOrAppUser,)

    def get_queryset(self):
        queryset = super().get_queryset()
        cluster_id = self.request.query_params.get('cluster_id')
        asset_group_id = self.request.query_params.get('asset_group_id')
        admin_user_id = self.request.query_params.get('admin_user_id')
        system_user_id = self.request.query_params.get('system_user_id')
        node_id = self.request.query_params.get("node_id")

        if cluster_id:
            queryset = queryset.filter(cluster__id=cluster_id)
        if asset_group_id:
            queryset = queryset.filter(groups__id=asset_group_id)
        if admin_user_id:
            admin_user = get_object_or_404(AdminUser, id=admin_user_id)
            assets_direct = [asset.id for asset in admin_user.asset_set.all()]
            clusters = [cluster.id for cluster in admin_user.cluster_set.all()]
            queryset = queryset.filter(Q(cluster__id__in=clusters)|Q(id__in=assets_direct))
        if system_user_id:
            system_user = get_object_or_404(SystemUser, id=system_user_id)
            clusters = system_user.get_clusters()
            queryset = queryset.filter(cluster__in=clusters)
        if node_id:
            node = get_object_or_404(Node, id=node_id)
            queryset = queryset.filter(nodes__key__startswith=node.key)
        return queryset


class UserAssetListView(generics.ListAPIView):
    queryset = Asset.objects.all()
    serializer_class = serializers.AssetSerializer
    permission_classes = (IsValidUser,)

    def get_queryset(self):
        assets_granted = get_user_granted_assets(self.request.user)
        queryset = self.queryset.filter(
            id__in=[asset.id for asset in assets_granted]
        )
        return queryset


class AssetListUpdateApi(IDInFilterMixin, ListBulkCreateUpdateDestroyAPIView):
    """
    Asset bulk update api
    """
    queryset = Asset.objects.all()
    serializer_class = serializers.AssetSerializer
    permission_classes = (IsSuperUser,)


class AssetRefreshHardwareApi(generics.RetrieveAPIView):
    """
    Refresh asset hardware info
    """
    queryset = Asset.objects.all()
    serializer_class = serializers.AssetSerializer
    permission_classes = (IsSuperUser,)

    def retrieve(self, request, *args, **kwargs):
        asset_id = kwargs.get('pk')
        asset = get_object_or_404(Asset, pk=asset_id)
        summary = update_asset_hardware_info_manual(asset)[1]
        logger.debug("Refresh summary: {}".format(summary))
        if summary.get('dark'):
            return Response(summary['dark'].values(), status=501)
        else:
            return Response({"msg": "ok"})


class AssetAdminUserTestApi(generics.RetrieveAPIView):
    """
    Test asset admin user connectivity
    """
    queryset = Asset.objects.all()
    permission_classes = (IsSuperUser,)

    def retrieve(self, request, *args, **kwargs):
        asset_id = kwargs.get('pk')
        asset = get_object_or_404(Asset, pk=asset_id)
        ok, msg = test_asset_connectability_manual(asset)
        if ok:
            return Response({"msg": "pong"})
        else:
            return Response({"error": msg}, status=502)