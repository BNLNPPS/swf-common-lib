git """
Test suite for BaseAgent multi-subscriber functionality.

Tests cover:
- Multiple subscription initialization
- Dynamic subscription management
- Subscription validation
- Reconnection with multiple subscriptions
- Backward compatibility
"""

import pytest
import json
from unittest.mock import Mock, MagicMock, patch, call
from swf_common_lib.base_agent import BaseAgent


class TestBaseAgentMultiSubscriber:
    """Test cases for multi-subscriber functionality."""

    @patch('swf_common_lib.base_agent.stomp.Connection')
    @patch('swf_common_lib.base_agent.get_next_agent_id')
    @patch('swf_common_lib.base_agent.load_testbed_config')
    def test_multiple_subscriptions_initialization(self, mock_config, mock_agent_id, mock_conn):
        """Test that agent initializes with multiple subscription queues."""
        # Arrange
        mock_config.return_value = Mock(namespace='test-namespace')
        mock_agent_id.return_value = 1
        
        subscription_queues = [
            '/queue/workflow_control',
            '/topic/system_events',
            '/queue/data_input'
        ]
        
        # Act
        agent = BaseAgent(
            agent_type='TEST',
            subscription_queues=subscription_queues
        )
        
        # Assert
        assert len(agent.subscription_queues) == 3
        assert '/queue/workflow_control' in agent.subscription_queues
        assert '/topic/system_events' in agent.subscription_queues
        assert '/queue/data_input' in agent.subscription_queues
        assert agent.subscription_queue == '/queue/workflow_control'  # First queue for backward compat

    @patch('swf_common_lib.base_agent.stomp.Connection')
    @patch('swf_common_lib.base_agent.get_next_agent_id')
    @patch('swf_common_lib.base_agent.load_testbed_config')
    def test_single_subscription_backward_compatibility(self, mock_config, mock_agent_id, mock_conn):
        """Test backward compatibility with single subscription_queue parameter."""
        # Arrange
        mock_config.return_value = Mock(namespace='test-namespace')
        mock_agent_id.return_value = 1
        
        # Act - using deprecated parameter
        with pytest.warns(UserWarning, match="deprecated.*subscription_queue"):
            agent = BaseAgent(
                agent_type='TEST',
                subscription_queue='/queue/single'
            )
        
        # Assert
        assert len(agent.subscription_queues) == 1
        assert agent.subscription_queues[0] == '/queue/single'
        assert agent.subscription_queue == '/queue/single'

    @patch('swf_common_lib.base_agent.stomp.Connection')
    @patch('swf_common_lib.base_agent.get_next_agent_id')
    @patch('swf_common_lib.base_agent.load_testbed_config')
    def test_subscription_validation_requires_prefix(self, mock_config, mock_agent_id, mock_conn):
        """Test that subscriptions must have /queue/ or /topic/ prefix."""
        # Arrange
        mock_config.return_value = Mock(namespace='test-namespace')
        mock_agent_id.return_value = 1
        
        # Act & Assert
        with pytest.raises(ValueError, match="must start with '/queue/' or '/topic/'"):
            BaseAgent(
                agent_type='TEST',
                subscription_queues=['invalid_queue']
            )

    @patch('swf_common_lib.base_agent.stomp.Connection')
    @patch('swf_common_lib.base_agent.get_next_agent_id')
    @patch('swf_common_lib.base_agent.load_testbed_config')
    def test_no_subscription_raises_error(self, mock_config, mock_agent_id, mock_conn):
        """Test that at least one subscription is required."""
        # Arrange
        mock_config.return_value = Mock(namespace='test-namespace')
        mock_agent_id.return_value = 1
        
        # Act & Assert
        with pytest.raises(ValueError, match="Either subscription_queue or subscription_queues"):
            BaseAgent(agent_type='TEST')

    @patch('swf_common_lib.base_agent.stomp.Connection')
    @patch('swf_common_lib.base_agent.get_next_agent_id')
    @patch('swf_common_lib.base_agent.load_testbed_config')
    def test_add_subscription_success(self, mock_config, mock_agent_id, mock_conn):
        """Test dynamically adding a new subscription."""
        # Arrange
        mock_config.return_value = Mock(namespace='test-namespace')
        mock_agent_id.return_value = 1
        mock_connection = MagicMock()
        mock_conn.return_value = mock_connection
        
        agent = BaseAgent(
            agent_type='TEST',
            subscription_queues=['/queue/initial']
        )
        agent.mq_connected = True
        agent._api_request = MagicMock(return_value={'status': 'ok'})
        
        # Act
        result = agent.add_subscription('/queue/new_queue')
        
        # Assert
        assert result is True
        assert '/queue/new_queue' in agent.subscription_queues
        assert len(agent.subscription_queues) == 2
        mock_connection.subscribe.assert_called_once_with(
            destination='/queue/new_queue',
            id=2,
            ack='auto'
        )

    @patch('swf_common_lib.base_agent.stomp.Connection')
    @patch('swf_common_lib.base_agent.get_next_agent_id')
    @patch('swf_common_lib.base_agent.load_testbed_config')
    def test_add_subscription_invalid_format(self, mock_config, mock_agent_id, mock_conn):
        """Test that add_subscription validates destination format."""
        # Arrange
        mock_config.return_value = Mock(namespace='test-namespace')
        mock_agent_id.return_value = 1
        
        agent = BaseAgent(
            agent_type='TEST',
            subscription_queues=['/queue/initial']
        )
        
        # Act & Assert
        with pytest.raises(ValueError, match="must start with '/queue/' or '/topic/'"):
            agent.add_subscription('invalid_format')

    @patch('swf_common_lib.base_agent.stomp.Connection')
    @patch('swf_common_lib.base_agent.get_next_agent_id')
    @patch('swf_common_lib.base_agent.load_testbed_config')
    def test_add_subscription_already_exists(self, mock_config, mock_agent_id, mock_conn):
        """Test adding a subscription that already exists."""
        # Arrange
        mock_config.return_value = Mock(namespace='test-namespace')
        mock_agent_id.return_value = 1
        
        agent = BaseAgent(
            agent_type='TEST',
            subscription_queues=['/queue/existing']
        )
        
        # Act
        result = agent.add_subscription('/queue/existing')
        
        # Assert
        assert result is True
        assert len(agent.subscription_queues) == 1  # Not duplicated

    @patch('swf_common_lib.base_agent.stomp.Connection')
    @patch('swf_common_lib.base_agent.get_next_agent_id')
    @patch('swf_common_lib.base_agent.load_testbed_config')
    def test_remove_subscription_success(self, mock_config, mock_agent_id, mock_conn):
        """Test dynamically removing a subscription."""
        # Arrange
        mock_config.return_value = Mock(namespace='test-namespace')
        mock_agent_id.return_value = 1
        mock_connection = MagicMock()
        mock_conn.return_value = mock_connection
        
        agent = BaseAgent(
            agent_type='TEST',
            subscription_queues=['/queue/queue1', '/queue/queue2']
        )
        agent.mq_connected = True
        agent._subscription_ids = {'/queue/queue1': 1, '/queue/queue2': 2}
        
        # Act
        result = agent.remove_subscription('/queue/queue1')
        
        # Assert
        assert result is True
        assert '/queue/queue1' not in agent.subscription_queues
        assert '/queue/queue2' in agent.subscription_queues
        mock_connection.unsubscribe.assert_called_once_with(id=1)

    @patch('swf_common_lib.base_agent.stomp.Connection')
    @patch('swf_common_lib.base_agent.get_next_agent_id')
    @patch('swf_common_lib.base_agent.load_testbed_config')
    def test_remove_subscription_not_subscribed(self, mock_config, mock_agent_id, mock_conn):
        """Test removing a subscription that doesn't exist."""
        # Arrange
        mock_config.return_value = Mock(namespace='test-namespace')
        mock_agent_id.return_value = 1
        
        agent = BaseAgent(
            agent_type='TEST',
            subscription_queues=['/queue/existing']
        )
        
        # Act
        result = agent.remove_subscription('/queue/nonexistent')
        
        # Assert
        assert result is False
        assert '/queue/existing' in agent.subscription_queues

    @patch('swf_common_lib.base_agent.stomp.Connection')
    @patch('swf_common_lib.base_agent.get_next_agent_id')
    @patch('swf_common_lib.base_agent.load_testbed_config')
    def test_get_subscriptions(self, mock_config, mock_agent_id, mock_conn):
        """Test retrieving current subscriptions."""
        # Arrange
        mock_config.return_value = Mock(namespace='test-namespace')
        mock_agent_id.return_value = 1
        
        subscription_queues = ['/queue/q1', '/queue/q2', '/topic/t1']
        agent = BaseAgent(
            agent_type='TEST',
            subscription_queues=subscription_queues
        )
        
        # Act
        subs = agent.get_subscriptions()
        
        # Assert
        assert len(subs) == 3
        assert '/queue/q1' in subs
        assert '/queue/q2' in subs
        assert '/topic/t1' in subs
        # Verify it returns a copy
        assert subs is not agent.subscription_queues

    @patch('swf_common_lib.base_agent.stomp.Connection')
    @patch('swf_common_lib.base_agent.get_next_agent_id')
    @patch('swf_common_lib.base_agent.load_testbed_config')
    def test_send_message_validation(self, mock_config, mock_agent_id, mock_conn):
        """Test that send_message validates destination format."""
        # Arrange
        mock_config.return_value = Mock(namespace='test-namespace')
        mock_agent_id.return_value = 1
        
        agent = BaseAgent(
            agent_type='TEST',
            subscription_queues=['/queue/input']
        )
        
        # Act & Assert - invalid format
        with pytest.raises(ValueError, match="must start with '/queue/' or '/topic/'"):
            agent.send_message('invalid_dest', {'msg_type': 'test'})

    @patch('swf_common_lib.base_agent.stomp.Connection')
    @patch('swf_common_lib.base_agent.get_next_agent_id')
    @patch('swf_common_lib.base_agent.load_testbed_config')
    def test_send_message_success(self, mock_config, mock_agent_id, mock_conn):
        """Test successful message sending."""
        # Arrange
        mock_config.return_value = Mock(namespace='test-namespace')
        mock_agent_id.return_value = 1
        mock_connection = MagicMock()
        mock_conn.return_value = mock_connection
        
        agent = BaseAgent(
            agent_type='TEST',
            subscription_queues=['/queue/input']
        )
        
        message = {'msg_type': 'test', 'data': 'value'}
        
        # Act
        agent.send_message('/queue/output', message)
        
        # Assert
        mock_connection.send.assert_called_once()
        call_args = mock_connection.send.call_args
        assert call_args[1]['destination'] == '/queue/output'
        
        # Check message includes auto-injected fields
        sent_body = json.loads(call_args[1]['body'])
        assert sent_body['msg_type'] == 'test'
        assert sent_body['data'] == 'value'
        assert 'sender' in sent_body
        assert 'namespace' in sent_body

    @patch('swf_common_lib.base_agent.stomp.Connection')
    @patch('swf_common_lib.base_agent.get_next_agent_id')
    @patch('swf_common_lib.base_agent.load_testbed_config')
    def test_register_subscribers_multiple(self, mock_config, mock_agent_id, mock_conn):
        """Test registering multiple subscribers."""
        # Arrange
        mock_config.return_value = Mock(namespace='test-namespace')
        mock_agent_id.return_value = 1
        
        agent = BaseAgent(
            agent_type='TEST',
            subscription_queues=['/queue/q1', '/queue/q2', '/topic/t1']
        )
        agent._api_request = MagicMock(return_value={'status': 'ok'})
        
        # Act
        result = agent.register_subscribers()
        
        # Assert
        assert result is True
        assert agent._api_request.call_count == 3  # One for each subscription

    @patch('swf_common_lib.base_agent.stomp.Connection')
    @patch('swf_common_lib.base_agent.get_next_agent_id')
    @patch('swf_common_lib.base_agent.load_testbed_config')
    def test_reconnect_resubscribes_all(self, mock_config, mock_agent_id, mock_conn):
        """Test that reconnection resubscribes to all queues."""
        # Arrange
        mock_config.return_value = Mock(namespace='test-namespace')
        mock_agent_id.return_value = 1
        mock_connection = MagicMock()
        mock_connection.is_connected.return_value = False
        mock_conn.return_value = mock_connection
        
        agent = BaseAgent(
            agent_type='TEST',
            subscription_queues=['/queue/q1', '/queue/q2', '/topic/t1']
        )
        agent.mq_connected = False
        
        # Act
        result = agent._attempt_reconnect()
        
        # Assert
        assert result is True
        assert agent.mq_connected is True
        
        # Verify all subscriptions were recreated
        assert mock_connection.subscribe.call_count == 3
        subscribe_calls = [call[1]['destination'] for call in mock_connection.subscribe.call_args_list]
        assert '/queue/q1' in subscribe_calls
        assert '/queue/q2' in subscribe_calls
        assert '/topic/t1' in subscribe_calls

    @patch('swf_common_lib.base_agent.stomp.Connection')
    @patch('swf_common_lib.base_agent.get_next_agent_id')
    @patch('swf_common_lib.base_agent.load_testbed_config')
    def test_mixed_queue_and_topic_subscriptions(self, mock_config, mock_agent_id, mock_conn):
        """Test that agent can subscribe to both queues and topics."""
        # Arrange
        mock_config.return_value = Mock(namespace='test-namespace')
        mock_agent_id.return_value = 1
        
        # Act
        agent = BaseAgent(
            agent_type='TEST',
            subscription_queues=[
                '/queue/point_to_point',
                '/topic/pub_sub',
                '/queue/another_queue',
                '/topic/another_topic'
            ]
        )
        
        # Assert
        queues = [s for s in agent.subscription_queues if s.startswith('/queue/')]
        topics = [s for s in agent.subscription_queues if s.startswith('/topic/')]
        
        assert len(queues) == 2
        assert len(topics) == 2
        assert len(agent.subscription_queues) == 4


class TestBaseAgentEdgeCases:
    """Test edge cases and error conditions."""

    @patch('swf_common_lib.base_agent.stomp.Connection')
    @patch('swf_common_lib.base_agent.get_next_agent_id')
    @patch('swf_common_lib.base_agent.load_testbed_config')
    def test_empty_subscription_list(self, mock_config, mock_agent_id, mock_conn):
        """Test that empty subscription list raises error."""
        # Arrange
        mock_config.return_value = Mock(namespace='test-namespace')
        mock_agent_id.return_value = 1
        
        # Act & Assert
        with pytest.raises(ValueError):
            BaseAgent(agent_type='TEST', subscription_queues=[])

    @patch('swf_common_lib.base_agent.stomp.Connection')
    @patch('swf_common_lib.base_agent.get_next_agent_id')
    @patch('swf_common_lib.base_agent.load_testbed_config')
    def test_add_subscription_when_disconnected(self, mock_config, mock_agent_id, mock_conn):
        """Test adding subscription when MQ is disconnected."""
        # Arrange
        mock_config.return_value = Mock(namespace='test-namespace')
        mock_agent_id.return_value = 1
        
        agent = BaseAgent(
            agent_type='TEST',
            subscription_queues=['/queue/initial']
        )
        agent.mq_connected = False
        agent._api_request = MagicMock(return_value={'status': 'ok'})
        
        # Act
        result = agent.add_subscription('/queue/new')
        
        # Assert - should succeed but not subscribe via STOMP yet
        assert result is True
        assert '/queue/new' in agent.subscription_queues

    @patch('swf_common_lib.base_agent.stomp.Connection')
    @patch('swf_common_lib.base_agent.get_next_agent_id')
    @patch('swf_common_lib.base_agent.load_testbed_config')
    def test_subscription_ids_tracking(self, mock_config, mock_agent_id, mock_conn):
        """Test that subscription IDs are properly tracked."""
        # Arrange
        mock_config.return_value = Mock(namespace='test-namespace')
        mock_agent_id.return_value = 1
        mock_connection = MagicMock()
        mock_conn.return_value = mock_connection
        
        agent = BaseAgent(
            agent_type='TEST',
            subscription_queues=['/queue/q1', '/queue/q2']
        )
        agent.mq_connected = True
        
        # Simulate subscription ID tracking during add
        agent._subscription_ids = {'/queue/q1': 1, '/queue/q2': 2}
        agent._api_request = MagicMock(return_value={'status': 'ok'})
        
        # Act
        agent.add_subscription('/queue/q3')
        
        # Assert
        assert len(agent._subscription_ids) == 3
        assert '/queue/q3' in agent._subscription_ids
        assert agent._subscription_ids['/queue/q3'] == 3


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
