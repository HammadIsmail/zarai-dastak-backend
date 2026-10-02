import graphene
from .types import UserType, VehicleType, BookingType
from .queries import Query
from .mutations import Mutation


# Create GraphQL Schema
schema = graphene.Schema(
    query=Query,
    mutation=Mutation,
    types=[UserType, VehicleType, BookingType]
)
