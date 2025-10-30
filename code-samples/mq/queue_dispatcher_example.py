#!/usr/bin/env python3
"""
Example: Queue Dispatcher for Fast Processing Workflow

Demonstrates dispatching work to queue-based workers:
- Send slice assignments to worker queue with task-id headers
- Send control messages via topic broadcast
- Track worker responses from results queue

This pattern is used by iDDS in the fast processing workflow.
"""

import json
import time
from swf_common_lib.base_agent import BaseAgent


class QueueDispatcher(BaseAgent):
    """
    Example dispatcher that sends TF slices to worker queues.
    Demonstrates fast processing workflow coordination patterns.
    """

    def __init__(self, task_id, debug=False):
        super().__init__(
            agent_type='queue-dispatcher',
            subscription_queue='/queue/panda.results.sub2',  # iDDS subscribes to sub2
            debug=debug
        )

        self.task_id = task_id
        self.slices_dispatched = 0
        self.slices_completed = 0

    def run(self):
        """Override run to demonstrate dispatching."""
        self.logger.info(f"Starting {self.agent_name} for task {self.task_id}...")
        self.logger.info(f"Connecting to ActiveMQ at {self.mq_host}:{self.mq_port}")

        self.mq_connected = False

        try:
            # Connect to broker
            self.conn.connect(
                self.mq_user,
                self.mq_password,
                wait=True,
                version='1.1',
                headers={
                    'client-id': self.agent_name,
                    'heart-beat': '30000,30000'
                }
            )
            self.mq_connected = True

            # Subscribe to results queue (auto-ack for dispatcher)
            self.conn.subscribe(
                destination=self.subscription_queue,
                id=1,
                ack='auto'
            )
            self.logger.info(f"Subscribed to results queue: '{self.subscription_queue}'")

            # Register and send initial heartbeat (non-fatal if fails)
            try:
                self.register_subscriber()
                self.send_heartbeat()
            except Exception as e:
                self.logger.warning(f"Heartbeat/registration failed (non-fatal for testing): {e}")

            # Dispatch some example slices
            self.logger.info("Dispatching example TF slices to workers...")
            for i in range(5):
                self.dispatch_slice(f"slice-{i}", f"stf-{i // 2}")
                time.sleep(1)

            self.logger.info(f"Dispatched {self.slices_dispatched} slices. Waiting for results...")

            # Wait for results
            timeout = 60
            start_time = time.time()
            while (time.time() - start_time) < timeout and self.slices_completed < self.slices_dispatched:
                time.sleep(5)
                # Send heartbeat (non-fatal if fails)
                try:
                    self.send_heartbeat()
                except Exception as e:
                    self.logger.warning(f"Heartbeat failed (non-fatal): {e}")

            # Send run end notification
            self.logger.info("Sending transformer end message...")
            self.send_transformer_end()

            self.logger.info(f"Completed: {self.slices_completed}/{self.slices_dispatched} slices")

        except KeyboardInterrupt:
            self.logger.info(f"Stopping {self.agent_name}...")
        except Exception as e:
            self.mq_connected = False
            self.logger.error(f"An error occurred: {e}")
            import traceback
            traceback.print_exc()
        finally:
            if self.conn and self.conn.is_connected():
                self.conn.disconnect()
                self.mq_connected = False
                self.logger.info("Disconnected from ActiveMQ.")

    def dispatch_slice(self, slice_id, stf_id):
        """
        Dispatch a TF slice to worker queue with task-id header.
        Workers filter messages by task-id to only receive their assigned work.
        """
        slice_message = {
            'slice_id': slice_id,
            'stf_id': stf_id,
            'task_id': self.task_id,
            'data_location': f'/data/stf/{stf_id}/slice_{slice_id}.raw'
        }

        # Send with task_id header for worker filtering (underscore for selector compatibility)
        headers = {
            'task_id': self.task_id,
            'persistent': 'true'
        }

        self.send_to_queue(
            queue_name='/queue/panda.transformer.slices',
            message_body=slice_message,
            headers=headers
        )

        self.slices_dispatched += 1
        self.logger.info(f"Dispatched slice {slice_id} to workers (task_id={self.task_id})")

    def send_transformer_end(self):
        """
        Broadcast transformer end message to all workers via topic.
        All workers subscribed to the topic will receive this message.
        """
        end_message = {
            'msg_type': 'transformer_end',
            'task_id': self.task_id,
            'timestamp': time.time()
        }

        # Use send_message for topics (broadcast)
        self.send_message(
            destination='/topic/panda.transformer',
            message_body=end_message
        )

        self.logger.info(f"Broadcasted transformer end for task {self.task_id}")

    def on_message(self, frame):
        """Handle result messages from workers."""
        try:
            destination = frame.headers.get('destination', '')

            if 'panda.results' in destination:
                message_data = json.loads(frame.body)
                slice_id = message_data.get('slice_id', 'unknown')
                status = message_data.get('status', 'unknown')
                worker = message_data.get('worker', 'unknown')

                self.logger.info(f"Received result for slice {slice_id}: {status} (from {worker})")

                if status == 'success':
                    self.slices_completed += 1

                # In real implementation, would update PanDA bookkeeping here

        except Exception as e:
            self.logger.error(f"Error handling result message: {e}")


def main():
    """Example usage of QueueDispatcher."""
    import sys

    if len(sys.argv) < 2:
        print("Usage: queue_dispatcher_example.py <task_id>")
        print("Example: queue_dispatcher_example.py task-12345")
        sys.exit(1)

    task_id = sys.argv[1]
    debug = '--debug' in sys.argv

    dispatcher = QueueDispatcher(task_id=task_id, debug=debug)
    dispatcher.run()


if __name__ == "__main__":
    main()
