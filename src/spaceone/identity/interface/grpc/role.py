from spaceone.core.pygrpc import BaseAPI
from spaceone.api.identity.v2 import role_pb2, role_pb2_grpc
from spaceone.identity.service.role_service import RoleService


class Role(BaseAPI, role_pb2_grpc.RoleServicer):
    pb2 = role_pb2
    pb2_grpc = role_pb2_grpc

    def create(self, request, context):
        params, metadata = self.parse_request(request, context)
        endpoint_svc = RoleService(metadata)
        response: dict = endpoint_svc.create(params)
        return self.dict_to_message(response)

    def update(self, request, context):
        params, metadata = self.parse_request(request, context)
        endpoint_svc = RoleService(metadata)
        response: dict = endpoint_svc.update(params)
        return self.dict_to_message(response)

    def delete(self, request, context):
        params, metadata = self.parse_request(request, context)
        endpoint_svc = RoleService(metadata)
        endpoint_svc.delete(params)
        return self.empty()

    def get(self, request, context):
        params, metadata = self.parse_request(request, context)
        endpoint_svc = RoleService(metadata)
        response: dict = endpoint_svc.get(params)
        return self.dict_to_message(response)

    def list(self, request, context):
        params, metadata = self.parse_request(request, context)
        endpoint_svc = RoleService(metadata)
        response: dict = endpoint_svc.list(params)
        return self.dict_to_message(response)

    def stat(self, request, context):
        params, metadata = self.parse_request(request, context)
        endpoint_svc = RoleService(metadata)
        response: dict = endpoint_svc.stat(params)
        return self.dict_to_message(response)
