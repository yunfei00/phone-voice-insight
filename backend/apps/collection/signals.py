from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.collection.models import CollectionSourceLease, CollectionTargetState
from apps.sources.models import DataSource, SourceTarget


@receiver(post_save, sender=SourceTarget)
def ensure_collection_target_state(
    sender: type[SourceTarget], instance: SourceTarget, created: bool, **kwargs: object
) -> None:
    del sender, created, kwargs
    CollectionTargetState.objects.get_or_create(source_target=instance)


@receiver(post_save, sender=DataSource)
def ensure_collection_source_lease(
    sender: type[DataSource], instance: DataSource, created: bool, **kwargs: object
) -> None:
    del sender, created, kwargs
    CollectionSourceLease.objects.get_or_create(source=instance)
