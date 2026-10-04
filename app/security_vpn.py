def log_suspicious_attempt(
    db: Session,
    ip: str,
    reason: str,
    user_agent: Optional[str] = None,
    extra_headers: Optional[dict] = None
) -> None:
    """
    Enregistre une tentative suspecte en base de données et dans le fichier de log.
    """
    security_logger.warning(
        f"Tentative bloquée | IP={ip} | Raison={reason} | "
        f"UA={user_agent} | Headers={extra_headers}"
    )

    if db is not None:
        try:
            from app.models import SecurityLog
            security_log = SecurityLog(
                ip_address=ip,
                reason=reason,
                user_agent=user_agent,
                headers=str(extra_headers),
                created_at=datetime.now(timezone.utc)
            )
            db.add(security_log)
            db.commit()
        except Exception as e:
            security_logger.error(f"Erreur enregistrement SecurityLog: {e}")
            db.rollback()
