#!/usr/bin/env python3
"""
Example: Queue-based Worker for Fast Processing Workflow

Demonstrates the new queue messaging capabilities in BaseAgent:
- Subscribe to work queue with manual acknowledgment
- Subscribe to control topic for broadcast messages
- Process messages with ack/nack
- Send results to dual-subscriber queue

This pattern is used by transformer workers in the fast processing workflow.
"""

import sys
import json
import time
from swf_common_lib.base_agent import BaseAgent


class QueueWorker(BaseAgent):
    """
    Example worker that processes TF slices from a queue.
    Demonstrates fast processing workflow message patterns.
    """

    def __init__(self, task_id, debug=False):
        # Initialize with primary subscription (optional, can be '/topic/unused' if not needed)
        super().__init__(
            agent_type='queue-worker',
            subscription_queue='/topic/workflow',  # Primary topic subscription
            debug=debug
        )

        self.task_id = task_id
        self.slices_processed = 0
        self.running = True

    def run(self):
        """Override run to set up queue subscriptions."""
        # Connect to ActiveMQ
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

            # Subscribe to primary workflow topic (broadcast messages)
            self.conn.subscribe(destination=self.subscription_queue, id=1, ack='auto')
            self.logger.info(f"Subscribed to workflow topic: '{self.subscription_queue}'")

            # Subscribe to TF slice queue with task-id filtering
            slice_queue = '/queue/panda.transformer.slices'
            # Use underscore instead of hyphen for selector compatibility
            selector = f"task_id = '{self.task_id}'"  # Only receive slices for this task
            self.subscribe_to_queue(
                queue_name=slice_queue,
                ack_mode='client-individual',  # Manual ack required
                prefetch_size=1,  # Only fetch one message at a time
                selector=selector
            )

            # Subscribe to control topic for run end notifications
            self.subscribe_to_topic('/topic/panda.transformer')

            # Register and send initial heartbeat (non-fatal if fails)
            try:
                self.register_subscriber()
                self.send_heartbeat()
            except Exception as e:
                self.logger.warning(f"Heartbeat/registration failed (non-fatal for testing): {e}")

            self.logger.info(f"{self.agent_name} is running. Processing slices for task {self.task_id}.")

            # Main loop
            while self.running:
                time.sleep(60)

                # Check connection and reconnect if needed
                if not self.mq_connected:
                    self._attempt_reconnect()

                # Send heartbeat (non-fatal if fails)
                try:
                    self.send_heartbeat()
                except Exception as e:
                    self.logger.warning(f"Heartbeat failed (non-fatal): {e}")

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

    def on_message(self, frame):
        """
        Handle incoming messages from multiple subscriptions.
        Routes messages based on destination.
        """
        destination = frame.headers.get('destination', '')
        subscription_id = frame.headers.get('subscription', '')

        try:
            if '/queue/panda.transformer.slices' in destination:
                # TF slice to process - requires manual ack
                self._handle_slice_message(frame)

            elif '/topic/panda.transformer' in destination:
                # Control message (broadcast)
                self._handle_control_message(frame)

            elif '/topic/workflow' in destination:
                # General workflow message
                self._handle_workflow_message(frame)

            else:
                self.logger.warning(f"Received message from unknown destination: {destination}")

        except Exception as e:
            self.logger.error(f"Error handling message: {e}")
            # Important: Don't ack message if processing failed
            if 'slice' in destination:
                self.nack_message(frame)

    def _handle_slice_message(self, frame):
        """
        Process a TF slice message.
        Must manually ack or nack based on processing result.
        """
        try:
            message_data = json.loads(frame.body)
            slice_id = message_data.get('slice_id', 'unknown')
            stf_id = message_data.get('stf_id', 'unknown')

            self.logger.info(f"Processing TF slice {slice_id} from STF {stf_id}")

            # Simulate slice processing (would call EICrecon here)
            time.sleep(2)  # Simulated processing time

            # Send result to dual-subscriber queue
            result = {
                'slice_id': slice_id,
                'stf_id': stf_id,
                'worker': self.agent_name,
                'status': 'success',
                'processing_time': 2.0
            }

            # Results queue has two consumers: PA (sub1) and iDDS (sub2)
            self.send_to_queue('/queue/panda.results', result)

            # Acknowledge message - removes from queue
            self.ack_message(frame)

            self.slices_processed += 1
            self.logger.info(f"Completed slice {slice_id}. Total processed: {self.slices_processed}")

        except Exception as e:
            self.logger.error(f"Failed to process slice: {e}")
            # Negative acknowledge - return message to queue for retry
            self.nack_message(frame)

    def _handle_control_message(self, frame):
        """Handle control messages like 'transformer end'."""
        try:
            message_data = json.loads(frame.body)
            msg_type = message_data.get('msg_type', 'unknown')

            if msg_type == 'transformer_end':
                task_id = message_data.get('task_id')
                if task_id == self.task_id:
                    self.logger.info(f"Received transformer end for task {self.task_id}")
                    self.logger.info("Entering soft-ending mode (will quit when queue empty)")
                    # In real implementation, would set flag and quit when no new messages
                    self.running = False

        except Exception as e:
            self.logger.error(f"Error handling control message: {e}")

    def _handle_workflow_message(self, frame):
        """Handle general workflow broadcast messages."""
        try:
            message_data, msg_type = self.log_received_message(frame)
            # Process workflow events as needed
        except Exception as e:
            self.logger.error(f"Error handling workflow message: {e}")


def main():
    """Example usage of QueueWorker."""
    import sys

    if len(sys.argv) < 2:
        print("Usage: queue_worker_example.py <task_id>")
        print("Example: queue_worker_example.py task-12345")
        sys.exit(1)

    task_id = sys.argv[1]
    debug = '--debug' in sys.argv

    worker = QueueWorker(task_id=task_id, debug=debug)
    worker.run()


if __name__ == "__main__":
    main()
