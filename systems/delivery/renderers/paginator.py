# systems/delivery/renderers/paginator.py
from __future__ import annotations

import logging
from typing import List

from systems.translation_pipeline.models.page_job import PageJob
from systems.delivery.renderers.message_builder import MessageBuilder

logger = logging.getLogger(__name__)

class Paginator:
    async def paginate(self, job: PageJob, page_num: int = 1, mode: str = "single_message") -> List[str]:
        file_name = job.file_name or "Unknown"

        if not job.page_data or not job.page_data.scenes:
            builder = MessageBuilder(page_num=page_num, msg_num=1, is_continuation=False, file_name=file_name)
            return [builder.build(is_last_message=True).replace("[[TOTAL_MSGS]]", "1")]

        scenes = job.page_data.scenes
        messages: List[str] = []
        current_builder = MessageBuilder(page_num=page_num, msg_num=1, is_continuation=False, file_name=file_name)

        for s_idx, scene in enumerate(scenes):
            is_last_scene = (s_idx == len(scenes) - 1)
            scene_header = current_builder.format_scene_header(scene)
            
            if not current_builder.can_fit(scene_header):
                messages.append(current_builder.build(is_last_message=False))
                current_builder = MessageBuilder(
                    page_num=page_num, msg_num=len(messages)+1,
                    is_continuation=(mode == "single_message"), file_name=file_name
                )
            
            current_builder.append_to_buffer(scene_header)

            for elem in scene.elements:
                formatted_elem = current_builder.format_element(elem)
                
                if current_builder.can_fit(formatted_elem):
                    current_builder.append_to_buffer(formatted_elem)
                else:
                    messages.append(current_builder.build(is_last_message=False))
                    current_builder = MessageBuilder(
                        page_num=page_num, msg_num=len(messages)+1,
                        is_continuation=True, file_name=file_name
                    )
                    if scene.scene_number:
                        cont_header = f"━━━━ ✨ *Scene {scene.scene_number}* ✨ ━━━━ \\(متابعة\\)\n\n"
                        current_builder.append_to_buffer(cont_header)
                    current_builder.append_to_buffer(formatted_elem)

            if mode == "scene_split" and not is_last_scene:
                if current_builder._buffer.strip():
                    messages.append(current_builder.build(is_last_message=False))
                    current_builder = MessageBuilder(
                        page_num=page_num, msg_num=len(messages)+1,
                        is_continuation=False, file_name=file_name
                    )

        messages.append(current_builder.build(is_last_message=True))
        total_msgs = str(len(messages))
        return [msg.replace("[[TOTAL_MSGS]]", total_msgs) for msg in messages]