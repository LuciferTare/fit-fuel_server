import datetime

from rest_framework.renderers import JSONRenderer


class ResponseRenderer(JSONRenderer):
    def render(self, data, accepted_media_type=None, renderer_context=None):
        status_code = renderer_context["response"].status_code
        response = {
            "data": data,
            "message": "",
            "status": status_code,
            "time": datetime.datetime.now(),
        }

        if not str(status_code).startswith("2"):
            response["data"] = None
            if isinstance(data, dict) and "detail" in data:
                response["message"] = data["detail"]
            elif data and isinstance(data, str):
                response["data"] = data
                response["message"] = data
            else:
                response["data"] = data
                response["message"] = data
                if isinstance(data, dict) and data.get("status", []):
                    code = data.get("status", [])[0].code
                    if code == 307:
                        response["data"] = data["data"][0]
                        response["status"] = code
        else:
            if data and "results" in data and "count" in data:
                response["data"] = data["results"]
                response["count"] = data["count"]
                response["next"] = data["next"]
                response["previous"] = data["previous"]
            elif data and isinstance(data, str):
                response["data"] = data
                response["message"] = data
            elif isinstance(data, dict):
                # Pop `detail` so it becomes the message but doesn't appear in data
                data_copy = dict(data)
                response["message"] = data_copy.pop("detail", "")
                response["data"] = data_copy
            else:
                response["data"] = data

        return super(ResponseRenderer, self).render(
            response, accepted_media_type, renderer_context
        )
