#!/usr/bin/env python3

import sys
import os
sys.path.append('/home/ec2-user/sprint4/seclore-rag-server/backend')

from onyx.chat.answer import Answer
from onyx.chat.models import AnswerStyleConfig, PromptConfig
from onyx.llm.interfaces import LLMConfig
from onyx.llm.chat_llm import DefaultMultiLLM
from onyx.tools.force import ForceUseTool

def test_summary_integration():
    """Test that conversation summary is properly integrated into system message"""
    
    # Create a minimal LLM config
    llm_config = LLMConfig(
        model_provider="openai",
        model_name="gpt-4",
        temperature=0.1,
        api_key="test-key"
    )
    
    # Create a test LLM instance
    llm = DefaultMultiLLM(
        api_key="test-key",
        timeout=30,
        model_provider="openai",
        model_name="gpt-4",
        temperature=0.1
    )
    
    # Create test prompt config
    prompt_config = PromptConfig(
        system_prompt="You are a helpful assistant.",
        task_prompt="Please answer the user's question.",
        datetime_aware=False,
        include_citations=False
    )
    
    # Create answer style config
    answer_style_config = AnswerStyleConfig()
    
    # Create force use tool config
    force_use_tool = ForceUseTool(force_use=False, tool_name="search")
    
    # Test conversation summary
    test_summary = "User asked about Python programming. Assistant explained basic concepts."
    
    # Create Answer instance with conversation summary
    answer = Answer(
        question="What is machine learning?",
        answer_style_config=answer_style_config,
        llm=llm,
        prompt_config=prompt_config,
        force_use_tool=force_use_tool,
        conversation_summary=test_summary
    )
    
    # Test the prompt builder creation (this should not fail)
    try:
        # This will trigger the processed_streamed_output property which builds the prompt
        prompt_builder = answer._Answer__create_prompt_builder()
        messages = prompt_builder.build()
        
        print("✓ Prompt building succeeded!")
        print(f"Number of messages: {len(messages)}")
        
        # Check if system message contains the summary
        for i, msg in enumerate(messages):
            print(f"Message {i}: {msg.type}")
            if msg.type == "system":
                print(f"System message content: {msg.content[:200]}...")
                if test_summary in msg.content:
                    print("✓ Summary found in system message!")
                else:
                    print("✗ Summary NOT found in system message!")
            
        # Check that last message is not a system message
        if messages and messages[-1].type != "system":
            print("✓ Last message is not a system message!")
        else:
            print("✗ Last message is a system message - this will cause an error!")
            
    except Exception as e:
        print(f"✗ Error during prompt building: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_summary_integration() 