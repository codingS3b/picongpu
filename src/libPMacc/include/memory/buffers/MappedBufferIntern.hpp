/**
 * Copyright 2014 Rene Widera, Axel Huebl
 *
 * This file is part of libPMacc.
 *
 * libPMacc is free software: you can redistribute it and/or modify
 * it under the terms of of either the GNU General Public License or
 * the GNU Lesser General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 * libPMacc is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
 * GNU General Public License and the GNU Lesser General Public License
 * for more details.
 *
 * You should have received a copy of the GNU General Public License
 * and the GNU Lesser General Public License along with libPMacc.
 * If not, see <http://www.gnu.org/licenses/>.
 */


#pragma once

#include <cassert>

#include "memory/buffers/Buffer.hpp"
#include "memory/buffers/DeviceBuffer.hpp"
#include "eventSystem/EventSystem.hpp"

#include "eventSystem/tasks/Factory.hpp"

namespace PMacc
{

/**
 * Implementation of the MappedBufferIntern interface.
 */
template <class TYPE, unsigned DIM>
class MappedBufferIntern : public DeviceBuffer<TYPE, DIM> // DeviceBufferIntern<TYPE, DIM>
{
public:

    typedef typename DeviceBuffer<TYPE, DIM>::DataBoxType DataBoxType;

    /**
     * constructor
     * @param dataSpace DataSpace describing the size of the HostBufferIntern to be created
     */
    MappedBufferIntern(DataSpace<DIM> dataSpace) throw (std::bad_alloc) :
    DeviceBuffer<TYPE, DIM>(dataSpace),
    pointer(NULL), ownPointer(true)
    {
        CUDA_CHECK(cudaMallocHost(&pointer, dataSpace.productOfComponents() * sizeof (TYPE), cudaHostAllocMapped));
        reset(false);
    }

    /**
     * destructor
     */
    virtual ~MappedBufferIntern() throw (std::runtime_error)
    {
        if (pointer && ownPointer)
        {
            CUDA_CHECK(cudaFreeHost(pointer));
        }
    }

    /*! Get pointer of memory
     * @return pointer to memory
     */
    TYPE* getBasePointer()
    {
        __startOperation(ITask::TASK_HOST);
        return (TYPE*) this->getCudaPitched().ptr;
    }

    TYPE* getPointer()
    {
        __startOperation(ITask::TASK_HOST);
        return (TYPE*) this->getCudaPitched().ptr;
    }

    void copyFrom(HostBuffer<TYPE, DIM>& other)
    {
        __startAtomicTransaction(__getTransactionEvent());
        assert(this->isMyDataSpaceGreaterThan(other.getCurrentDataSpace()));
        Factory::getInstance().createTaskCopyHostToDevice(other, *this);
        __setTransactionEvent(__endTransaction());
    }

    void copyFrom(DeviceBuffer<TYPE, DIM>& other)
    {
        __startAtomicTransaction(__getTransactionEvent());
        assert(this->isMyDataSpaceGreaterThan(other.getCurrentDataSpace()));
        Factory::getInstance().createTaskCopyDeviceToDevice(other, *this);
        __setTransactionEvent(__endTransaction());
    }

    void reset(bool preserveData = true)
    {
        __startOperation(ITask::TASK_HOST);
        this->setCurrentSize(this->getDataSpace().productOfComponents());
        if (!preserveData)
            memset(pointer, 0, this->getDataSpace().productOfComponents() * sizeof (TYPE));
    }

    void setValue(const TYPE& value)
    {
        __startOperation(ITask::TASK_HOST);
        size_t current_size = this->getCurrentSize();
        for (size_t i = 0; i < current_size; i++)
        {
            pointer[i] = value;
        }
    }

    bool hasCurrentSizeOnDevice() const
    {
        return false;
    }
    
    virtual size_t* getCurrentSizeHostSidePointer()
    {
        return this->current_size;
    }

    size_t* getCurrentSizeOnDevicePointer() throw (std::runtime_error)
    {
        return NULL;
    }

    DataSpace<DIM> getOffset() const
    {
        return DataSpace<DIM>();
    }

    void setCurrentSize(const size_t size)
    {
        Buffer<TYPE, DIM>::setCurrentSize(size);
    }

    const cudaPitchedPtr getCudaPitched() const
    {
        __startOperation(ITask::TASK_CUDA);
        TYPE* dPointer;
        cudaHostGetDevicePointer(&dPointer, pointer, 0);

        return make_cudaPitchedPtr(dPointer,
                                   this->data_space.x() * sizeof (TYPE),
                                   this->data_space.x(),
                                   this->data_space.y()
                                   );
    }
    
    size_t getPitch() const
    {
        return this->data_space.x() * sizeof (TYPE);
    }

    DataBoxType getHostDataBox()
    {
        __startOperation(ITask::TASK_HOST);
        return DataBoxType(PitchedBox<TYPE, DIM > (pointer, DataSpace<DIM > (),
                                                   this->data_space, this->data_space[0] * sizeof (TYPE)));
    }

    DataBoxType getDataBox()
    {
        __startOperation(ITask::TASK_CUDA);
        TYPE* dPointer;
        cudaHostGetDevicePointer(&dPointer, pointer, 0);
        return DataBoxType(PitchedBox<TYPE, DIM > (dPointer, DataSpace<DIM > (),
                                                   this->data_space, this->data_space[0] * sizeof (TYPE)));
    }

private:
    TYPE* pointer;
    bool ownPointer;
};

}