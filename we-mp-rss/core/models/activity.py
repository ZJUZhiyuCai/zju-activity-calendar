from .base import Base, Column, String, Integer, Text


class Activity(Base):
    """官网/公众号活动持久化模型"""
    __tablename__ = "activities"

    id = Column(String(255), primary_key=True)
    title = Column(String(1000), nullable=False)
    college_id = Column(String(255), index=True)
    college_name = Column(String(255))
    activity_type = Column(String(100))
    activity_date = Column(String(20), index=True)
    activity_time = Column(String(100))
    location = Column(String(500))
    speaker = Column(String(500))
    speaker_title = Column(String(500))
    speaker_intro = Column(Text)
    organizer = Column(String(500))
    description = Column(Text)
    cover_image = Column(String(500))
    source_url = Column(String(500))
    source_type = Column(String(50))
    source_channel = Column(String(50), default="website")
    raw_date_text = Column(String(200))
    mp_name = Column(String(255))
    publish_time = Column(Integer)
    registration_required = Column(Integer, default=0)
    registration_link = Column(String(500))
    fetched_at = Column(Integer, index=True)  # unix timestamp

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "college_id": self.college_id,
            "college_name": self.college_name,
            "activity_type": self.activity_type,
            "activity_date": self.activity_date,
            "activity_time": self.activity_time,
            "location": self.location,
            "speaker": self.speaker,
            "speaker_title": self.speaker_title,
            "speaker_intro": self.speaker_intro,
            "organizer": self.organizer,
            "description": self.description,
            "cover_image": self.cover_image,
            "source_url": self.source_url,
            "source_type": self.source_type,
            "source_channel": self.source_channel,
            "raw_date_text": self.raw_date_text,
            "mp_name": self.mp_name,
            "publish_time": self.publish_time,
            "registration_required": bool(self.registration_required),
            "registration_link": self.registration_link,
        }
