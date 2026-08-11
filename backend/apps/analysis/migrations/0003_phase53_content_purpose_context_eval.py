from django.db import migrations, models


CONTENT_PURPOSE_CHOICES = [
    ("PRODUCT_EXPERIENCE", "产品体验"),
    ("QUESTION", "问题咨询"),
    ("RESOURCE_SHARE", "资源分享"),
    ("PHOTO_SHARE", "图片作品分享"),
    ("TUTORIAL", "教程"),
    ("SOCIAL_INTERACTION", "社交互动"),
    ("PROMOTIONAL", "宣传"),
    ("METADATA_REPLY", "元数据回复"),
    ("OTHER", "其他"),
]


class Migration(migrations.Migration):
    dependencies = [("analysis", "0002_analysisbatch_analysisevaluation_and_more")]

    operations = [
        migrations.AddField(
            model_name="analysisresult",
            name="content_purpose",
            field=models.CharField(
                choices=CONTENT_PURPOSE_CHOICES,
                db_index=True,
                default="OTHER",
                max_length=30,
                verbose_name="内容用途",
            ),
        ),
        migrations.AddField(
            model_name="analysisevaluation",
            name="context_correct",
            field=models.BooleanField(default=False, verbose_name="上下文使用正确"),
            preserve_default=False,
        ),
    ]
