"""Upload synthetic DICOM files to the source Orthanc for testing.

Usage:
    python scripts/seed_source.py [--count 5]

Generates minimal valid DICOM instances using pydicom and uploads
them to the source PACS via its REST API.
"""
import argparse
import io
from datetime import datetime, timedelta

import httpx
import pydicom
from pydicom.dataset import Dataset, FileDataset
from pydicom.uid import generate_uid

SOURCE_URL = "http://localhost:8043"
SOURCE_USER = "orthanc"
SOURCE_PASS = "orthanc"


def create_test_dicom(
    patient_id: str,
    patient_name: str,
    study_uid: str,
    series_uid: str,
    instance_uid: str,
    study_date: str,
    modality: str = "CT",
) -> bytes:
    """Create a minimal valid DICOM file in memory."""
    ds = Dataset()
    ds.PatientID = patient_id
    ds.PatientName = patient_name
    ds.StudyInstanceUID = study_uid
    ds.SeriesInstanceUID = series_uid
    ds.SOPInstanceUID = instance_uid
    ds.SOPClassUID = "1.2.840.10008.5.1.4.1.1.2"  # CT Image Storage
    ds.StudyDate = study_date
    ds.Modality = modality
    ds.StudyDescription = f"Test {modality} Study"
    ds.AccessionNumber = f"ACC{patient_id[-3:]}"
    ds.Rows = 2
    ds.Columns = 2
    ds.BitsAllocated = 8
    ds.BitsStored = 8
    ds.HighBit = 7
    ds.PixelRepresentation = 0
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.PixelData = b"\x00\x01\x02\x03"

    ds.is_little_endian = True
    ds.is_implicit_VR = True

    buffer = io.BytesIO()
    file_ds = FileDataset(
        filename_or_obj=buffer,
        dataset=ds,
        file_meta=_file_meta(instance_uid),
        preamble=b"\x00" * 128,
    )
    file_ds.save_as(buffer)
    return buffer.getvalue()


def _file_meta(sop_instance_uid: str):
    meta = pydicom.Dataset()
    meta.MediaStorageSOPClassUID = "1.2.840.10008.5.1.4.1.1.2"
    meta.MediaStorageSOPInstanceUID = sop_instance_uid
    meta.TransferSyntaxUID = "1.2.840.10008.1.2"  # Implicit VR Little Endian
    meta.FileMetaInformationVersion = b"\x00\x01"
    meta.FileMetaInformationGroupLength = 0  # pydicom recalculates
    meta.ImplementationClassUID = generate_uid()
    return meta


def upload_to_orthanc(dicom_bytes: bytes):
    resp = httpx.post(
        f"{SOURCE_URL}/instances",
        content=dicom_bytes,
        headers={"Content-Type": "application/dicom"},
        auth=(SOURCE_USER, SOURCE_PASS),
    )
    resp.raise_for_status()
    return resp.json()


def main():
    parser = argparse.ArgumentParser(description="Seed source PACS with test DICOM data")
    parser.add_argument("--count", type=int, default=5, help="Number of test studies to create")
    args = parser.parse_args()

    modalities = ["CT", "MR", "CR", "DX", "US"]
    base_date = datetime(2024, 1, 1)

    for i in range(args.count):
        patient_id = f"PAT{i:04d}"
        patient_name = f"TEST^PATIENT^{i}"
        study_uid = generate_uid()
        series_uid = generate_uid()
        instance_uid = generate_uid()
        study_date = (base_date + timedelta(days=i * 7)).strftime("%Y%m%d")
        modality = modalities[i % len(modalities)]

        dicom_bytes = create_test_dicom(
            patient_id=patient_id,
            patient_name=patient_name,
            study_uid=study_uid,
            series_uid=series_uid,
            instance_uid=instance_uid,
            study_date=study_date,
            modality=modality,
        )
        result = upload_to_orthanc(dicom_bytes)
        print(f"Uploaded study {i + 1}/{args.count}: {patient_id} ({modality}) -> {result.get('ID', 'ok')}")

    print(f"\nDone. {args.count} test studies uploaded to source PACS at {SOURCE_URL}")


if __name__ == "__main__":
    main()
