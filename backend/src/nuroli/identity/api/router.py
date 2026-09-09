"""Identity HTTP routes. Feature tickets add endpoints here and nowhere else."""

from fastapi import APIRouter

router = APIRouter(tags=["identity"])
