"""
Functions for interacting with flow ORM objects.
Intended for internal use by the Orion API.
"""

from typing import List
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import delete, select

from prefect.orion import schemas
from prefect.orion.database.dependencies import inject_db_interface


@inject_db_interface
async def create_flow(
    session: sa.orm.Session,
    flow: schemas.core.Flow,
    db_interface=None,
):
    """
    Creates a new flow.

    If a flow with the same name already exists, the existing flow is returned.

    Args:
        session: a database session
        flow: a flow model

    Returns:
        db_interface.Flow: the newly-created or existing flow
    """

    insert_stmt = (
        (await db_interface.insert(db_interface.Flow))
        .values(**flow.dict(shallow=True, exclude_unset=True))
        .on_conflict_do_nothing(
            index_elements=db_interface.flow_unique_upsert_columns,
        )
    )
    await session.execute(insert_stmt)

    query = (
        sa.select(db_interface.Flow)
        .where(
            db_interface.Flow.name == flow.name,
        )
        .limit(1)
        .execution_options(populate_existing=True)
    )
    result = await session.execute(query)
    model = result.scalar()
    return model


@inject_db_interface
async def update_flow(
    session: sa.orm.Session,
    flow_id: UUID,
    flow: schemas.actions.FlowUpdate,
    db_interface=None,
):
    """
    Updates a flow.

    Args:
        session: a database session
        flow_id: the flow id to update
        flow: a flow update model

    Returns:
        bool: whether or not matching rows were found to update
    """

    if not isinstance(flow, schemas.actions.FlowUpdate):
        raise ValueError(
            f"Expected parameter flow to have type schemas.actions.FlowUpdate, got {type(flow)!r} instead"
        )

    update_stmt = (
        sa.update(db_interface.Flow).where(db_interface.Flow.id == flow_id)
        # exclude_unset=True allows us to only update values provided by
        # the user, ignoring any defaults on the model
        .values(**flow.dict(shallow=True, exclude_unset=True))
    )
    result = await session.execute(update_stmt)
    return result.rowcount > 0


@inject_db_interface
async def read_flow(session: sa.orm.Session, flow_id: UUID, db_interface=None):
    """
    Reads a flow by id.

    Args:
        session: A database session
        flow_id: a flow id

    Returns:
        db_interface.Flow: the flow
    """
    return await session.get(db_interface.Flow, flow_id)


@inject_db_interface
async def read_flow_by_name(session: sa.orm.Session, name: str, db_interface=None):
    """
    Reads a flow by name.

    Args:
        session: A database session
        name: a flow name

    Returns:
        db_interface.Flow: the flow
    """

    result = await session.execute(select(db_interface.Flow).filter_by(name=name))
    return result.scalar()


@inject_db_interface
async def _apply_flow_filters(
    query,
    flow_filter: schemas.filters.FlowFilter = None,
    flow_run_filter: schemas.filters.FlowRunFilter = None,
    task_run_filter: schemas.filters.TaskRunFilter = None,
    deployment_filter: schemas.filters.DeploymentFilter = None,
    db_interface=None,
):
    """
    Applies filters to a flow query as a combination of EXISTS subqueries.
    """

    if flow_filter:
        query = query.where((await flow_filter.as_sql_filter()))

    if deployment_filter:
        exists_clause = select(db_interface.Deployment).where(
            db_interface.Deployment.flow_id == db_interface.Flow.id,
            (await deployment_filter.as_sql_filter()),
        )
        query = query.where(exists_clause.exists())

    if flow_run_filter or task_run_filter:
        exists_clause = select(db_interface.FlowRun).where(
            db_interface.FlowRun.flow_id == db_interface.Flow.id
        )

        if flow_run_filter:
            exists_clause = exists_clause.where((await flow_run_filter.as_sql_filter()))

        if task_run_filter:
            exists_clause = exists_clause.join(
                db_interface.TaskRun,
                db_interface.TaskRun.flow_run_id == db_interface.FlowRun.id,
            ).where((await task_run_filter.as_sql_filter()))

        query = query.where(exists_clause.exists())

    return query


@inject_db_interface
async def read_flows(
    session: sa.orm.Session,
    flow_filter: schemas.filters.FlowFilter = None,
    flow_run_filter: schemas.filters.FlowRunFilter = None,
    task_run_filter: schemas.filters.TaskRunFilter = None,
    deployment_filter: schemas.filters.DeploymentFilter = None,
    offset: int = None,
    limit: int = None,
    db_interface=None,
):
    """
    Read multiple flows.

    Args:
        session: A database session
        flow_filter: only select flows that match these filters
        flow_run_filter: only select flows whose flow runs match these filters
        task_run_filter: only select flows whose task runs match these filters
        deployment_filter: only select flows whose deployments match these filters
        offset: Query offset
        limit: Query limit

    Returns:
        List[db_interface.Flow]: flows
    """

    query = select(db_interface.Flow).order_by(db_interface.Flow.name)

    query = await _apply_flow_filters(
        query,
        flow_filter=flow_filter,
        flow_run_filter=flow_run_filter,
        task_run_filter=task_run_filter,
        deployment_filter=deployment_filter,
        db_interface=db_interface,
    )

    if offset is not None:
        query = query.offset(offset)

    if limit is not None:
        query = query.limit(limit)

    result = await session.execute(query)
    return result.scalars().unique().all()


@inject_db_interface
async def count_flows(
    session: sa.orm.Session,
    flow_filter: schemas.filters.FlowFilter = None,
    flow_run_filter: schemas.filters.FlowRunFilter = None,
    task_run_filter: schemas.filters.TaskRunFilter = None,
    deployment_filter: schemas.filters.DeploymentFilter = None,
    db_interface=None,
) -> int:
    """
    Count flows.

    Args:
        session: A database session
        flow_filter: only count flows that match these filters
        flow_run_filter: only count flows whose flow runs match these filters
        task_run_filter: only count flows whose task runs match these filters
        deployment_filter: only count flows whose deployments match these filters

    Returns:
        int: count of flows
    """

    query = select(sa.func.count(sa.text("*"))).select_from(db_interface.Flow)

    query = await _apply_flow_filters(
        query,
        flow_filter=flow_filter,
        flow_run_filter=flow_run_filter,
        task_run_filter=task_run_filter,
        deployment_filter=deployment_filter,
        db_interface=db_interface,
    )

    result = await session.execute(query)
    return result.scalar()


@inject_db_interface
async def delete_flow(
    session: sa.orm.Session, flow_id: UUID, db_interface=None
) -> bool:
    """
    Delete a flow by id.

    Args:
        session: A database session
        flow_id: a flow id

    Returns:
        bool: whether or not the flow was deleted
    """

    result = await session.execute(
        delete(db_interface.Flow).where(db_interface.Flow.id == flow_id)
    )
    return result.rowcount > 0
