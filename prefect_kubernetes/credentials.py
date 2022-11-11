"""Module for defining Kubernetes credential handling and client generation."""

from contextlib import contextmanager
from typing import Generator, Literal, Optional, Union

from kubernetes import config as kube_config
from kubernetes.client import ApiClient, AppsV1Api, BatchV1Api, Configuration, CoreV1Api
from kubernetes.config.config_exception import ConfigException
from prefect.blocks.core import Block
from prefect.blocks.kubernetes import KubernetesClusterConfig
from prefect.utilities.collections import listrepr

KubernetesClient = Union[AppsV1Api, BatchV1Api, CoreV1Api]

K8S_CLIENT_TYPES = {
    "apps": AppsV1Api,
    "batch": BatchV1Api,
    "core": CoreV1Api,
}


class KubernetesCredentials(Block):
    """Credentials block for generating configured Kubernetes API clients.

    Attributes:
        cluster_config: A `KubernetesClusterConfig` block holding a JSON kube
            config for a specific kubernetes context.

    Examples:
        Load stored Kubernetes credentials:
        ```python
        from prefect_kubernetes.credentials import KubernetesCredentials

        kubernetes_credentials = KubernetesCredentials.load("my-k8s-credentials")
        ```

        Create resource-specific API clients from KubernetesCredentials:
        ```python
        from kubernetes.client.models import AppsV1Api, BatchV1Api, CoreV1Api
        from prefect_kubernetes import KubernetesCredentials

        kubernetes_credentials = KubernetesCredentials.load("my-k8s-credentials")

        with kubernetes_credentials.get_client("apps") as v1_apps_client:
            assert isinstance(v1_apps_client, AppsV1Api)

        with kubernetes_credentials.get_client("batch") as v1_batch_client:
            assert isinstance(v1_batch_client, BatchV1Api)

        with kubernetes_credentials.get_client("core") as v1_core_client:
            assert isinstance(v1_core_client, CoreV1Api)
        ```

        Create a namespaced job:
        ```python
        from prefect import flow
        from prefect_kubernetes import KubernetesCredentials
        from prefect_kubernetes.job import create_namespaced_job

        from kubernetes.client.models import V1Job

        kubernetes_credentials = KubernetesCredentials.load("my-k8s-credentials")

        @flow
        def kubernetes_orchestrator():
            create_namespaced_job(
                kubernetes_credentials=kubernetes_credentials,
                body=V1Job(**{"metadata": {"name": "my-job"}}),
            )
        ```
    """

    _block_type_name = "Kubernetes Credentials"
    _logo_url = "https://images.ctfassets.net/zscdif0zqppk/oYuHjIbc26oilfQSEMjRv/a61f5f6ef406eead2df5231835b4c4c2/logo.png?h=250"  # noqa

    cluster_config: Optional[KubernetesClusterConfig] = None

    @contextmanager
    def get_client(
        self,
        client_type: Literal["apps", "batch", "core"],
        configuration: Optional[Configuration] = None,
    ) -> Generator[KubernetesClient, None, None]:
        """Convenience method for retrieving a Kubernetes API client for deployment resources.

        Args:
            client_type: The resource-specific type of Kubernetes client to retrieve.

        Yields:
            An authenticated, resource-specific Kubernetes API client.

        Example:
            ```python
            from prefect_kubernetes.credentials import KubernetesCredentials

            with KubernetesCredentials.get_client("core") as core_v1_client:
                for pod in core_v1_client.list_namespaced_pod():
                    print(pod.metadata.name)
            ```
        """
        client_config = configuration or Configuration()

        with ApiClient(configuration=client_config) as generic_client:
            try:
                yield self.get_resource_specific_client(client_type)
            finally:
                generic_client.rest_client.pool_manager.clear()

    def get_resource_specific_client(
        self,
        client_type: str,
    ) -> Union[AppsV1Api, BatchV1Api, CoreV1Api]:
        """
        Utility function for configuring a generic Kubernetes client.
        It will attempt to connect to a Kubernetes cluster in three steps with
        the first successful connection attempt becoming the mode of communication with
        a cluster:

        1. It will first attempt to use a `KubernetesCredentials` block's
        `cluster_config` to configure a client using
        `KubernetesClusterConfig.configure_client`.

        2. Attempt in-cluster connection (will only work when running on a pod).

        3. Attempt out-of-cluster connection using the default location for a
        kube config file.

        Args:
            client_type: The Kubernetes API client type for interacting with specific
                Kubernetes resources.

        Returns:
            KubernetesClient: An authenticated, resource-specific Kubernetes Client.

        Raises:
            ValueError: If `client_type` is not a valid Kubernetes API client type.
        """

        if self.cluster_config:
            self.cluster_config.configure_client()
        else:
            try:
                kube_config.load_incluster_config()
            except ConfigException:
                kube_config.load_kube_config()

        try:
            return K8S_CLIENT_TYPES[client_type]()
        except KeyError:
            raise ValueError(
                f"Invalid client type provided '{client_type}'."
                f" Must be one of {listrepr(K8S_CLIENT_TYPES.keys())}."
            )
