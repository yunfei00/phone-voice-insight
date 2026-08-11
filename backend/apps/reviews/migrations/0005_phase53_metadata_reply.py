from django.db import migrations, models


EXCLUSION_CHOICES = [
    ("NONE", "不排除"),
    ("EMPTY_CONTENT", "空内容"),
    ("OFFICIAL_CONTENT", "官方内容"),
    ("PRODUCT_NOT_MATCHED", "产品不相关"),
    ("PAGE_NOISE", "页面噪声"),
    ("PROMOTIONAL", "宣传内容"),
    ("LOW_INFORMATION", "低信息"),
    ("DUPLICATE", "重复"),
    ("INVALID_ENCODING", "无效编码"),
    ("PARSER_ARTIFACT", "解析残留"),
    ("NO_PRODUCT_EXPERIENCE_SIGNAL", "无产品体验信号"),
    ("SOCIAL_INTERACTION", "纯社交互动"),
    ("RESOURCE_SHARE", "资源分享"),
    ("PHOTO_SHARE", "图片作品分享"),
    ("METADATA_REPLY", "纯元数据回复"),
    ("OTHER", "其他"),
]

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
    dependencies = [("reviews", "0004_phase52_experience_signal")]

    operations = [
        migrations.AlterField(
            model_name="analysiscorpusitem",
            name="exclusion_reason",
            field=models.CharField(
                choices=EXCLUSION_CHOICES,
                db_index=True,
                default="NONE",
                max_length=30,
                verbose_name="排除原因",
            ),
        ),
        migrations.AlterField(
            model_name="reviewquality",
            name="content_purpose",
            field=models.CharField(
                choices=CONTENT_PURPOSE_CHOICES,
                db_index=True,
                default="OTHER",
                max_length=30,
                verbose_name="内容用途",
            ),
        ),
        migrations.AlterField(
            model_name="reviewquality",
            name="exclusion_reason",
            field=models.CharField(
                choices=EXCLUSION_CHOICES,
                db_index=True,
                default="NONE",
                max_length=30,
                verbose_name="排除原因",
            ),
        ),
        migrations.AlterField(
            model_name="reviewqualityrun",
            name="content_purpose",
            field=models.CharField(
                choices=CONTENT_PURPOSE_CHOICES,
                default="OTHER",
                max_length=30,
                verbose_name="内容用途",
            ),
        ),
        migrations.AlterField(
            model_name="reviewqualityrun",
            name="exclusion_reason",
            field=models.CharField(
                choices=EXCLUSION_CHOICES,
                default="NONE",
                max_length=30,
                verbose_name="排除原因",
            ),
        ),
    ]
