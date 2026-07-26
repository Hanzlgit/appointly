from rest_framework import serializers


class DashboardStatusSummarySerializer(serializers.Serializer):
    """今日预约状态汇总。"""

    pending = serializers.IntegerField()
    confirmed = serializers.IntegerField()
    completed = serializers.IntegerField()
    cancelled = serializers.IntegerField()
    no_show = serializers.IntegerField()


class DashboardTrendPointSerializer(serializers.Serializer):
    """单日预约趋势点。"""

    date = serializers.DateField()
    count = serializers.IntegerField()


class DashboardLocationCountSerializer(serializers.Serializer):
    """按地点预约数量。"""

    location_id = serializers.IntegerField()
    location_name = serializers.CharField()
    count = serializers.IntegerField()


class DashboardResourceUtilizationSerializer(serializers.Serializer):
    """资源占用率。"""

    resource_id = serializers.IntegerField()
    resource_name = serializers.CharField()
    booked_minutes = serializers.IntegerField()
    available_minutes = serializers.IntegerField()
    utilization_rate = serializers.FloatField()


class DashboardPopularServiceSerializer(serializers.Serializer):
    """热门服务。"""

    service_id = serializers.IntegerField()
    service_name = serializers.CharField()
    count = serializers.IntegerField()


class DashboardSummaryResponseSerializer(serializers.Serializer):
    """经营看板汇总响应。"""

    reference_date = serializers.DateField()
    today_summary = DashboardStatusSummarySerializer()
    seven_day_trend = DashboardTrendPointSerializer(many=True)
    bookings_by_location = DashboardLocationCountSerializer(many=True)
    resource_utilization = DashboardResourceUtilizationSerializer(many=True)
    popular_services = DashboardPopularServiceSerializer(many=True)
