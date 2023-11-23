from mongoengine import *
from datetime import datetime
from spaceone.core.error import *
from spaceone.core.model.mongo_model import MongoModel


class Domain(MongoModel):
    domain_id = StringField(max_length=40, generate_id="domain", unique=True)
    name = StringField(max_length=255)
    state = StringField(max_length=20, default="ENABLED")
    tags = DictField(default=None)
    created_at = DateTimeField(auto_now_add=True)
    deleted_at = DateTimeField(default=None, null=True)

    meta = {
        "updatable_fields": [
            "name",
            "state",
            "tags",
            "deleted_at",
        ],
        "minimal_fields": [
            "domain_id",
            "name",
            "state",
        ],
        "ordering": ["name"],
        "indexes": [
            # 'domain_id',
            "state",
        ],
    }

    @queryset_manager
    def objects(doc_cls, queryset):
        return queryset.filter(state__ne="DELETED")

    @classmethod
    def create(cls, data):
        domain_vos = cls.filter(name=data["name"])
        if domain_vos.count() > 0:
            raise ERROR_NOT_UNIQUE(key="name", value=data["name"])

        return super().create(data)

    def update(self, data):
        if "name" in data:
            domain_vos = self.filter(name=data["name"], domain_id__ne=self.domain_id)
            if domain_vos.count() > 0:
                raise ERROR_NOT_UNIQUE(key="name", value=data["name"])

        return super().update(data)

    def delete(self):
        self.update({"state": "DELETED", "deleted_at": datetime.utcnow()})
