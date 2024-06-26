#!/bin/python3

# Copyright (c) 2024 Humanitarian OpenStreetMap Team
#
#     This program is free software: you can redistribute it and/or modify
#     it under the terms of the GNU General Public License as published by
#     the Free Software Foundation, either version 3 of the License, or
#     (at your option) any later version.
#
#     OSM-Fieldwork is distributed in the hope that it will be useful,
#     but WITHOUT ANY WARRANTY; without even the implied warranty of
#     MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#     GNU General Public License for more details.
#
#     You should have received a copy of the GNU General Public License
#     along with OSM-Fieldwork.  If not, see <https:#www.gnu.org/licenses/>.
#
"""The async counterpart to OdkCentral.py, an ODK Central API client."""

import logging
import os
from asyncio import gather
from typing import Optional
from uuid import uuid4

import aiohttp

log = logging.getLogger(__name__)


class OdkCentral(object):
    def __init__(
        self,
        url: Optional[str] = None,
        user: Optional[str] = None,
        passwd: Optional[str] = None,
    ):
        """A Class for accessing an ODK Central server via it's REST API.

        Args:
            url (str): The URL of the ODK Central
            user (str): The user's account name on ODK Central
            passwd (str):  The user's account password on ODK Central
            session (str): Pass in an existing session for reuse.

        Returns:
            (OdkCentral): An instance of this class
        """
        if not url:
            url = os.getenv("ODK_CENTRAL_URL", default=None)
        self.url = url
        if not user:
            user = os.getenv("ODK_CENTRAL_USER", default=None)
        self.user = user
        if not passwd:
            passwd = os.getenv("ODK_CENTRAL_PASSWD", default=None)
        self.passwd = passwd
        verify = os.getenv("ODK_CENTRAL_SECURE", default=True)
        if type(verify) == str:
            self.verify = verify.lower() in ("true", "1", "t")
        else:
            self.verify = verify

        # Base URL for the REST API
        self.version = "v1"
        self.base = f"{self.url}/{self.version}/"

    def __enter__(self):
        """Sync context manager not allowed."""
        raise RuntimeError("Must be called with async context manager 'async with'")

    def __exit__(self):
        """Sync context manager not allowed."""
        raise RuntimeError("Must be called with async context manager 'async with'")

    async def __aenter__(self):
        """Async object instantiation."""
        # Header enables persistent connection, creates a cookie for this session
        self.session = aiohttp.ClientSession(
            raise_for_status=True,
            headers={"accept": "odkcentral"},
        )
        await self.authenticate()
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        """Async object close."""
        if self.session:
            await self.session.close()

    async def authenticate(self):
        """Authenticate to an ODK Central server."""
        async with self.session.post(f"{self.base}sessions", json={"email": self.user, "password": self.passwd}) as response:
            token = (await response.json())["token"]
            self.session.headers.update({"Authorization": f"Bearer {token}"})


class OdkProject(OdkCentral):
    """Class to manipulate a project on an ODK Central server."""

    def __init__(
        self,
        url: Optional[str] = None,
        user: Optional[str] = None,
        passwd: Optional[str] = None,
    ):
        """Args:
            url (str): The URL of the ODK Central
            user (str): The user's account name on ODK Central
            passwd (str):  The user's account password on ODK Central.

        Returns:
            (OdkProject): An instance of this object
        """
        super().__init__(url, user, passwd)

    async def listForms(self, projectId: int, metadata: bool = False):
        """Fetch a list of forms in a project on an ODK Central server.

        Args:
            projectId (int): The ID of the project on ODK Central

        Returns:
            (list): The list of XForms in this project
        """
        url = f"{self.base}projects/{projectId}/forms"
        headers = {}
        if metadata:
            headers.update({"X-Extended-Metadata": "true"})
        try:
            async with self.session.get(url, ssl=self.verify, headers=headers) as response:
                self.forms = await response.json()
                return self.forms
        except aiohttp.ClientError as e:
            log.error(f"Error fetching forms: {e}")
            return []

    async def listSubmissions(self, projectId: int, xform: str, filters: dict = None):
        """Fetch a list of submission instances for a given form.

        Returns data in format:

        {
            "value":[],
            "@odata.context": "URL/v1/projects/52/forms/103.svc/$metadata#Submissions",
            "@odata.count":0
        }

        Args:
            projectId (int): The ID of the project on ODK Central
            xform (str): The XForm to get the details of from ODK Central

        Returns:
            (json): The JSON of Submissions.
        """
        url = f"{self.base}projects/{projectId}/forms/{xform}.svc/Submissions"
        try:
            async with self.session.get(url, params=filters, ssl=self.verify) as response:
                return await response.json()
        except aiohttp.ClientError as e:
            log.error(f"Error fetching submissions: {e}")
            return {}

    async def getAllProjectSubmissions(self, projectId: int, xforms: list = None, filters: dict = None):
        """Fetch a list of submissions in a project on an ODK Central server.

        Args:
            projectId (int): The ID of the project on ODK Central
            xforms (list): The list of XForms to get the submissions of

        Returns:
            (json): All of the submissions for all of the XForm in a project
        """
        log.info(f"Getting all submissions for ODK project ({projectId}) forms ({xforms})")
        submission_data = []

        submission_tasks = [self.listSubmissions(projectId, task, filters) for task in xforms]
        submissions = await gather(*submission_tasks, return_exceptions=True)

        for submission in submissions:
            if isinstance(submission, Exception):
                log.error(f"Failed to get submissions: {submission}")
                continue
            log.debug(f"There are {len(submission['value'])} submissions")
            submission_data.extend(submission["value"])

        return submission_data


class OdkEntity(OdkCentral):
    """Class to manipulate a Entity on an ODK Central server."""

    def __init__(
        self,
        url: Optional[str] = None,
        user: Optional[str] = None,
        passwd: Optional[str] = None,
    ):
        """Args:
            url (str): The URL of the ODK Central
            user (str): The user's account name on ODK Central
            passwd (str):  The user's account password on ODK Central.

        Returns:
            (OdkEntity): An instance of this object.
        """
        super().__init__(url, user, passwd)

    async def listDatasets(
        self,
        projectId: int,
    ):
        """Get all Entity datasets (entity lists) for a project.

        JSON response:
        [
            {
                "name": "people",
                "createdAt": "2018-01-19T23:58:03.395Z",
                "projectId": 1,
                "approvalRequired": true
            }
        ]

        Args:
            projectId (int): The ID of the project on ODK Central.

        Returns:
            list: a list of JSON dataset metadata.
        """
        url = f"{self.base}projects/{projectId}/datasets/"
        try:
            async with self.session.get(url, ssl=self.verify) as response:
                return await response.json()
        except aiohttp.ClientError as e:
            log.error(f"Error fetching datasets: {e}")
            return []

    async def listEntities(
        self,
        projectId: int,
        datasetName: str,
    ):
        """Get all Entities for a project dataset (entity list).

        JSON format:
        [
        {
            "uuid": "uuid:85cb9aff-005e-4edd-9739-dc9c1a829c44",
            "createdAt": "2018-01-19T23:58:03.395Z",
            "updatedAt": "2018-03-21T12:45:02.312Z",
            "deletedAt": "2018-03-21T12:45:02.312Z",
            "creatorId": 1,
            "currentVersion": {
            "label": "John (88)",
            "current": true,
            "createdAt": "2018-03-21T12:45:02.312Z",
            "creatorId": 1,
            "userAgent": "Enketo/3.0.4",
            "version": 1,
            "baseVersion": null,
            "conflictingProperties": null
            }
        }
        ]

        Args:
            projectId (int): The ID of the project on ODK Central.
            datasetName (str): The name of a dataset, specific to a project.

        Returns:
            list: a list of JSON entity metadata, for a dataset.
        """
        url = f"{self.base}projects/{projectId}/datasets/{datasetName}/entities"
        try:
            async with self.session.get(url, ssl=self.verify) as response:
                return await response.json()
        except aiohttp.ClientError as e:
            log.error(f"Error fetching entities: {e}")
            return []

    async def createEntity(
        self,
        projectId: int,
        datasetName: str,
        label: str,
        data: dict,
    ) -> dict:
        """Create a new Entity in a project dataset (entity list).

        JSON request:
        {
        "uuid": "54a405a0-53ce-4748-9788-d23a30cc3afa",
        "label": "John Doe (88)",
        "data": {
            "firstName": "John",
            "age": "88"
        }
        }

        Args:
            projectId (int): The ID of the project on ODK Central.
            datasetName (int): The name of a dataset, specific to a project.
            label (str): Label for the Entity.
            data (dict): Key:Value pairs to insert as Entity data.

        Returns:
            dict: JSON of entity details.
                The 'uuid' field includes the unique entity identifier.
        """
        # The CSV must contain a geometry field to work
        # TODO also add this validation to uploadMedia if CSV format

        required_fields = ["geometry"]
        if not all(key in data for key in required_fields):
            msg = "'geometry' data field is mandatory"
            log.debug(msg)
            raise ValueError(msg)

        url = f"{self.base}projects/{projectId}/datasets/{datasetName}/entities"
        try:
            async with self.session.post(
                url,
                ssl=self.verify,
                json={
                    "uuid": str(uuid4()),
                    "label": label,
                    "data": data,
                },
            ) as response:
                return await response.json()
        except aiohttp.ClientError as e:
            log.error(f"Failed to create Entity: {e}")
            return {}

    async def createEntities(
        self,
        projectId: int,
        datasetName: str,
        labelDataDict: dict,
    ) -> list:
        """Bulk create Entities in a project dataset (entity list).

        NOTE this endpoint will be redundant after Central 2024.01 release.

        Args:
            projectId (int): The ID of the project on ODK Central.
            datasetName (int): The name of a dataset, specific to a project.
            labelDataDict (dict): Mapping of Entity label:data (str:dict) to insert.

        Returns:
            list: A list of Entity detail JSONs.
                The 'uuid' field includes the unique entity identifier.
        """
        log.info(f"Bulk uploading Entities for project ({projectId}) dataset ({datasetName})")
        entity_data = []

        entity_tasks = [self.createEntity(projectId, datasetName, label, data) for label, data in labelDataDict.items()]
        entities = await gather(*entity_tasks, return_exceptions=True)

        for entity in entities:
            if isinstance(entity, Exception):
                log.error(f"Failed to upload entity: {entity}")
                continue
            entity_data.append(entity)

        return entity_data

    async def updateEntity(
        self,
        projectId: int,
        datasetName: str,
        entityUuid: str,
        label: Optional[str] = None,
        data: Optional[dict] = None,
        newVersion: Optional[int] = None,
    ):
        """Update an existing Entity in a project dataset (entity list).

        The JSON request format is the same as creating, minus the 'uuid' field.
        The PATCH will only update the specific fields specified, leaving the
            remainder.

        If no 'newVersion' param is provided, the entity will be force updated
            in place.
        If 'newVersion' is provided, this must be a single integer increment
            from the current version.

        Args:
            projectId (int): The ID of the project on ODK Central.
            datasetName (int): The name of a dataset, specific to a project.
            entityUuid (str): Unique itentifier of the entity.
            label (str): Label for the Entity.
            data (dict): Key:Value pairs to insert as Entity data.
            newVersion (int): Integer version to increment to (current version + 1).

        Returns:
            dict: JSON of entity details.
                The 'uuid' field includes the unique entity identifier.
        """
        if not label and not data:
            msg = "One of either the 'label' or 'data' fields must be passed"
            log.debug(msg)
            raise ValueError(msg)

        json_data = {}
        if data:
            json_data["data"] = data
        if label:
            json_data["label"] = label

        url = f"{self.base}projects/{projectId}/datasets/{datasetName}/entities/{entityUuid}"
        if newVersion:
            url = f"{url}?baseVersion={newVersion - 1}"
        else:
            url = f"{url}?force=true"

        try:
            async with self.session.patch(
                url,
                ssl=self.verify,
                json=json_data,
            ) as response:
                return await response.json()
        except aiohttp.ClientError as e:
            log.error(f"Failed to update Entity: {e}")
            return {}

    async def deleteEntity(
        self,
        projectId: int,
        datasetName: str,
        entityUuid: str,
    ):
        """Delete an Entity in a project dataset (entity list).

        Only performs a soft deletion, so the Entity is actually archived.

        Args:
            projectId (int): The ID of the project on ODK Central.
            datasetName (int): The name of a dataset, specific to a project.
            entityUuid (str): Unique itentifier of the entity.

        Returns:
            bool: Deletion successful or not.
        """
        url = f"{self.base}projects/{projectId}/datasets/{datasetName}/entities/{entityUuid}"
        log.debug(f"Deleting dataset ({datasetName}) entity UUID ({entityUuid})")
        try:
            async with self.session.delete(url, ssl=self.verify) as response:
                success = (response_msg := await response.json()).get("success", False)
                if not success:
                    log.debug(f"Server returned deletion unsuccessful: {response_msg}")
                return success
        except aiohttp.ClientError as e:
            log.error(f"Failed to delete Entity: {e}")
            return False

    async def getEntityData(
        self,
        projectId: int,
        datasetName: str,
    ):
        """Get a lightweight JSON of the entity data fields in a dataset.

        Example response JSON:
        [
        {
            "0": {
                "__id": "523699d0-66ec-4cfc-a76b-4617c01c6b92",
                "label": "the_label_you_defined",
                "__system": {
                    "createdAt": "2024-03-24T06:30:31.219Z",
                    "creatorId": "7",
                    "creatorName": "fmtm@hotosm.org",
                    "updates": 4,
                    "updatedAt": "2024-03-24T07:12:55.871Z",
                    "version": 5,
                    "conflict": null
                },
                "geometry": "javarosa format geometry",
                "user_defined_field2": "text",
                "user_defined_field2": "text",
                "user_defined_field3": "test"
            }
        }
        ]

        Args:
            projectId (int): The ID of the project on ODK Central.
            datasetName (int): The name of a dataset, specific to a project.

        Returns:
            list: All entity data for a project dataset.
        """
        url = f"{self.base}projects/{projectId}/datasets/{datasetName}.svc/Entities"
        try:
            async with self.session.get(url, ssl=self.verify) as response:
                return (await response.json()).get("value", {})
        except aiohttp.ClientError as e:
            log.error(f"Failed to get Entity data: {e}")
            return {}
