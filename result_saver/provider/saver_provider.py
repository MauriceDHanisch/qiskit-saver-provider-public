import gzip
import json
import os
import warnings
import datetime
from typing import Optional, Any, Union


from qiskit.providers import JobV1, JobStatus

from result_saver.job import SavedJob
from result_saver.json import ResultSaverDecoder, ResultSaverEncoder

from qiskit_ibm_provider import IBMProvider
from qiskit.providers.backend import BackendV1 as Backend

from Scratch import find_and_create_scratch, update_metadata, metadata_loader


class SaverProvider(IBMProvider):
    ROOT_DIR = find_and_create_scratch()
    DEFAULT_SAVE_LOCATION = f"{ROOT_DIR}/jobs"
    FORMAT = "{date_str}-{job_id}.json.gz"

    def __init__(self, save_location: Optional[str] = None) -> None:
        super().__init__()
        self.save_location = save_location or self.DEFAULT_SAVE_LOCATION

    def get_backend(self,
                    name: str = None,
                    instance: Optional[str] = None,
                    **kwargs: Any,
                    ) -> Backend:
        """Return a monkey patched backend."""
        backend = super().get_backend(name, **kwargs)
        self.patch_backend(backend)
        return backend

    def patch_backend(self, backend):
        if not hasattr(backend, 'original_run'):  # Avoid patching multiple times
            backend.original_run = backend.run  # Store the original run method
            backend.run = self.new_run.__get__(
                backend)  # Replace run with new_run

    def new_run(self, metadata: dict, *args, **kwargs):
        warnings.warn("updating metadata")
        # Call the original run method
        job = self.original_run(*args, **kwargs)
        # Update metadata
        update_metadata(job, self.name, metadata)
        return job

    def retrieve_job(self, job_id: str, _ignore_running = False, overwrite = False) -> JobV1:
        """Return a single job.

        Args:
            job_id: The ID of the job to retrieve.

        Returns:
            The job with the given id.
        """
        filename = self.__job_local_filename(job_id)
        if filename is None or overwrite:

            md = metadata_loader(_extract=True)
            if md[md['job_id'] == job_id].job_status.values in ["JobStatus.ERROR", "JobStatus.CANCELLED"]:
                warnings.warn(
                    f"Job ID {job_id} has 'JobStatus.ERROR' or 'JobStatus.CANCELLED'. Aborting...")
                return None

            if _ignore_running:
                if md[md['job_id'] == job_id].job_status.values in ["JobStatus.RUNNING", "JobStatus.QUEUED"]:
                    warnings.warn(
                        f"Job ID {job_id} has status running/queued in md and _ignore_running = True. Aborting...")
                    return None
                
            warnings.warn(
                f"Job ID {job_id} not found in {self.save_location}. Retrieving it from the IBMQ provider...") if filename is None else None
            warnings.warn(
                f"Overwriting job ID {job_id} in {self.save_location}...") if overwrite else None
            
            ibm_prov = IBMProvider()
            ibm_job = ibm_prov.retrieve_job(job_id)

            additional_dict = {"job_status": str(ibm_job.status())}
            update_metadata(ibm_job, "None_Backend", additional_dict)

            if ibm_job.status() in [JobStatus.RUNNING, JobStatus.QUEUED]:
                warnings.warn(f"Job ID {job_id} is still running. Aborting...")
                return None
            if ibm_job.status() == JobStatus.DONE:
                self.save_job(ibm_job, overwrite=overwrite)
                additional_dict = {"execution_date": str(ibm_job.result().date)}
                update_metadata(ibm_job, "None_Backend", additional_dict)
                return ibm_job
            else:
                warnings.warn(
                    f"Job ID {job_id} is in an unknown state. Updating Metadata & Aborting...")
                return None

        try:
            with gzip.GzipFile(filename, "r") as f:
                job_str = str(f.read(), "utf8")
            job = json.loads(job_str, cls=ResultSaverDecoder)
            return job
        except Exception as e:
            raise RuntimeError(
                f"Failed to retrieve job for job id {job_id}.", e)

    def __save_location(self):
        return os.path.expanduser(self.save_location)

    def __job_saved_name(self, job_id: str) -> str:
        date_str = datetime.datetime.now().strftime("%Y.%m.%d-%Hh%M")
        return self.FORMAT.format(date_str=date_str, job_id=job_id)


    def __job_local_filename(self, job_id: str) -> Union[str, None]:
        save_location = self.__save_location()
        for filename in os.listdir(save_location):
            if job_id in filename:
                return os.path.join(save_location, filename)
        return None

    def __create_dir_if_doesnt_exist(self):
        if not os.path.exists(self.__save_location()):
            os.makedirs(self.__save_location())

    def save_job(self, job: JobV1, overwrite: bool = False) -> str:
        filename = self.__job_local_filename(job.job_id())
        if filename and not overwrite:
            warnings.warn(f"Job ID {job.job_id()} already saved and overwrite=False. Skipping...")
            return None
        
        # If no existing filename is found, or overwrite is True, proceed to save the job
        if not filename:
            filename = os.path.join(self.__save_location(), self.__job_saved_name(job.job_id()))
        
        job = SavedJob.from_job(job)
        try:
            self.__create_dir_if_doesnt_exist()
            job_str = json.dumps(job, cls=ResultSaverEncoder)
            with gzip.GzipFile(filename, "w") as f:
                f.write(bytes(job_str, "utf8"))
            return filename
        except Exception as e:
            raise RuntimeError(f"Failed to save job {job.job_id()}", e)