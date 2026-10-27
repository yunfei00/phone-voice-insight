from rest_framework import serializers


class ThreadTreeQuerySerializer(serializers.Serializer):
    product = serializers.IntegerField(required=False, min_value=1)
    source_filter = serializers.CharField(required=False, max_length=100)
    search = serializers.CharField(required=False, allow_blank=True, max_length=200, trim_whitespace=True)
    published_at_after = serializers.DateTimeField(required=False)
    published_at_before = serializers.DateTimeField(required=False)
    activity_at_after = serializers.DateTimeField(required=False)
    activity_at_before = serializers.DateTimeField(required=False)
    ordering = serializers.ChoiceField(
        required=False,
        default="latest_reply",
        choices=("latest_reply", "latest_thread", "reply_count", "view_count", "like_count"),
    )

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        for prefix in ("published_at", "activity_at"):
            after = attrs.get(f"{prefix}_after")
            before = attrs.get(f"{prefix}_before")
            if after and before and after > before:  # type: ignore[operator]
                raise serializers.ValidationError({f"{prefix}_after": "起始时间不能晚于结束时间。"})
        return attrs
